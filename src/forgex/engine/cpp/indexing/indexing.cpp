
#include "indexing.hpp"

#include "../core/core.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <iterator>
#include <system_error>
#include <unordered_set>
#include <utility>

namespace forgex::indexing {

namespace {

std::string lowercase(std::string value) {
    std::transform(
        value.begin(),
        value.end(),
        value.begin(),
        [](unsigned char character) {
            return static_cast<char>(std::tolower(character));
        }
    );

    return value;
}

bool path_is_inside(
    const std::filesystem::path& child,
    const std::filesystem::path& parent
) {
    auto child_it = child.begin();
    auto parent_it = parent.begin();

    for (; parent_it != parent.end(); ++parent_it, ++child_it) {
        if (child_it == child.end() || *child_it != *parent_it) {
            return false;
        }
    }

    return true;
}

} // namespace

std::string RepositoryIndexer::normalize_path(
    const std::filesystem::path& path
) {
    return path.lexically_normal().generic_string();
}

bool RepositoryIndexer::is_hidden(
    const std::filesystem::path& path
) {
    const std::string name = path.filename().string();

    return !name.empty() && name.front() == '.';
}

bool RepositoryIndexer::is_excluded_directory(
    const std::filesystem::path& path,
    const IndexOptions& options
) {
    const std::string name = lowercase(path.filename().string());

    for (const std::string& excluded : options.excluded_directories) {
        if (name == lowercase(excluded)) {
            return true;
        }
    }

    return false;
}

bool RepositoryIndexer::is_allowed_extension(
    const std::filesystem::path& path,
    const IndexOptions& options
) {
    if (options.extensions.empty()) {
        return true;
    }

    const std::string extension =
        lowercase(path.extension().string());

    for (const std::string& allowed : options.extensions) {
        if (extension == lowercase(allowed)) {
            return true;
        }
    }

    return false;
}

std::size_t RepositoryIndexer::count_lines(
    std::string_view content
) {
    if (content.empty()) {
        return 0;
    }

    return static_cast<std::size_t>(
        std::count(content.begin(), content.end(), '\n')
    ) + (content.back() == '\n' ? 0 : 1);
}

std::string RepositoryIndexer::normalize_case(
    std::string_view value,
    bool case_sensitive
) {
    std::string result(value);

    if (!case_sensitive) {
        result = lowercase(std::move(result));
    }

    return result;
}

std::optional<IndexedFile> RepositoryIndexer::read_and_index(
    const std::filesystem::path& file,
    const std::filesystem::path& root,
    std::size_t max_file_size_bytes
) {
    std::error_code error;

    const auto canonical_root =
        std::filesystem::canonical(root, error);

    if (error) {
        return std::nullopt;
    }

    const auto canonical_file =
        std::filesystem::canonical(file, error);

    if (
        error ||
        !path_is_inside(canonical_file, canonical_root)
    ) {
        return std::nullopt;
    }

    const auto file_status =
        std::filesystem::status(canonical_file, error);

    if (
        error ||
        !std::filesystem::is_regular_file(file_status)
    ) {
        return std::nullopt;
    }

    const auto file_size =
        std::filesystem::file_size(canonical_file, error);

    if (error || file_size > max_file_size_bytes) {
        return std::nullopt;
    }

    std::ifstream stream(
        canonical_file,
        std::ios::binary
    );

    if (!stream.is_open()) {
        return std::nullopt;
    }

    // Use braces to avoid the Most Vexing Parse.
    std::string content{
        std::istreambuf_iterator<char>(stream),
        std::istreambuf_iterator<char>()
    };

    if (stream.bad() || content.size() > max_file_size_bytes) {
        return std::nullopt;
    }

    if (forgex::core::CoreEngine::is_binary_data(content)) {
        return std::nullopt;
    }

    const auto relative = std::filesystem::relative(
        canonical_file,
        canonical_root,
        error
    );

    if (error || relative.empty() || relative.is_absolute()) {
        return std::nullopt;
    }

    IndexedFile indexed;

    indexed.path = normalize_path(relative);
    indexed.extension = lowercase(
        canonical_file.extension().string()
    );

    indexed.content_hash =
        forgex::core::CoreEngine::hash_string(content);

    indexed.size_bytes = content.size();
    indexed.line_count = count_lines(content);
    indexed.content = std::move(content);
    indexed.binary = false;

    return indexed;
}

IndexingResult RepositoryIndexer::index_directory(
    const std::filesystem::path& root,
    const IndexOptions& options
) {
    IndexingResult result;

    std::error_code error;

    const auto canonical_root =
        std::filesystem::canonical(root, error);

    if (
        error ||
        !std::filesystem::is_directory(canonical_root)
    ) {
        result.success = false;

        result.errors.push_back({
            root.string(),
            "Workspace directory does not exist or is inaccessible"
        });

        return result;
    }

    std::unordered_set<std::string> discovered_paths;
    bool scan_truncated = false;

    std::filesystem::recursive_directory_iterator iterator(
        canonical_root,
        std::filesystem::directory_options::skip_permission_denied,
        error
    );

    const std::filesystem::recursive_directory_iterator end;

    while (iterator != end) {
        if (error) {
            result.errors.push_back({
                canonical_root.string(),
                error.message()
            });

            error.clear();
            iterator.increment(error);
            continue;
        }

        const auto current = iterator->path();

        std::error_code status_error;

        const auto symlink_status =
            iterator->symlink_status(status_error);

        if (status_error) {
            result.errors.push_back({
                current.string(),
                status_error.message()
            });

            iterator.increment(error);
            continue;
        }

        if (std::filesystem::is_symlink(symlink_status)) {
            iterator.disable_recursion_pending();
            ++result.skipped_count;
            iterator.increment(error);
            continue;
        }

        if (iterator->is_directory(status_error)) {
            if (
                is_excluded_directory(current, options) ||
                (!options.include_hidden && is_hidden(current))
            ) {
                iterator.disable_recursion_pending();
            }

            iterator.increment(error);
            continue;
        }

        if (!iterator->is_regular_file(status_error)) {
            ++result.skipped_count;
            iterator.increment(error);
            continue;
        }

        if (
            !options.include_hidden &&
            is_hidden(current.filename())
        ) {
            ++result.skipped_count;
            iterator.increment(error);
            continue;
        }

        if (!is_allowed_extension(current, options)) {
            ++result.skipped_count;
            iterator.increment(error);
            continue;
        }

        ++result.discovered_count;

        if (
            options.max_files > 0 &&
            result.discovered_count > options.max_files
        ) {
            // A capped scan is incomplete: never prune entries that may
            // simply be beyond the configured scan limit.
            scan_truncated = true;
            ++result.skipped_count;
            iterator.increment(error);
            continue;
        }

        auto indexed = read_and_index(
            current,
            canonical_root,
            options.max_file_size_bytes
        );

        if (!indexed.has_value()) {
            ++result.skipped_count;
            iterator.increment(error);
            continue;
        }

        const std::string key = indexed->path;

        discovered_paths.insert(key);

        auto existing = files_.find(key);

        if (
            existing != files_.end() &&
            existing->second.content_hash == indexed->content_hash
        ) {
            ++result.unchanged_count;
        } else {
            if (existing == files_.end()) {
                ++result.indexed_count;
            } else {
                ++result.updated_count;
            }

            files_[key] = std::move(*indexed);
        }

        iterator.increment(error);
    }

    if (options.remove_missing_files && !scan_truncated) {
        for (auto it = files_.begin(); it != files_.end();) {
            if (discovered_paths.find(it->first) ==
                discovered_paths.end()) {
                it = files_.erase(it);
                ++result.removed_count;
            } else {
                ++it;
            }
        }
    }

    if (!result.errors.empty()) {
        result.success = false;
    }

    return result;
}

std::optional<IndexedFile> RepositoryIndexer::index_file(
    const std::filesystem::path& file,
    const std::filesystem::path& root,
    std::size_t max_file_size_bytes
) {
    auto indexed = read_and_index(
        file,
        root,
        max_file_size_bytes
    );

    if (!indexed.has_value()) {
        return std::nullopt;
    }

    files_[indexed->path] = *indexed;

    return indexed;
}

bool RepositoryIndexer::remove_file(
    std::string_view relative_path
) {
    return files_.erase(std::string(relative_path)) > 0;
}

void RepositoryIndexer::clear() {
    files_.clear();
}

std::optional<IndexedFile> RepositoryIndexer::get_file(
    std::string_view relative_path
) const {
    const auto found = files_.find(std::string(relative_path));

    if (found == files_.end()) {
        return std::nullopt;
    }

    return found->second;
}

std::vector<IndexedFile> RepositoryIndexer::get_all_files() const {
    std::vector<IndexedFile> result;

    result.reserve(files_.size());

    for (const auto& entry : files_) {
        result.push_back(entry.second);
    }

    std::sort(
        result.begin(),
        result.end(),
        [](const IndexedFile& left, const IndexedFile& right) {
            return left.path < right.path;
        }
    );

    return result;
}

std::vector<IndexedFile> RepositoryIndexer::search_content(
    std::string_view query,
    bool case_sensitive,
    std::size_t max_results
) const {
    std::vector<IndexedFile> result;

    if (query.empty()) {
        return result;
    }

    const std::string target =
        normalize_case(query, case_sensitive);

    for (const auto& entry : files_) {
        const IndexedFile& file = entry.second;

        const std::string content =
            normalize_case(file.content, case_sensitive);

        if (content.find(target) != std::string::npos) {
            result.push_back(file);
        }
    }

    std::sort(
        result.begin(),
        result.end(),
        [](const IndexedFile& left, const IndexedFile& right) {
            return left.path < right.path;
        }
    );

    if (max_results > 0 && result.size() > max_results) {
        result.resize(max_results);
    }

    return result;
}

std::size_t RepositoryIndexer::file_count() const noexcept {
    return files_.size();
}

} // namespace forgex::indexing
