
#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace forgex::indexing {

struct IndexOptions {
    std::size_t max_file_size_bytes = 2 * 1024 * 1024;
    std::size_t max_files = 100000;

    bool include_hidden = false;
    bool remove_missing_files = true;

    std::vector<std::string> extensions;
    std::vector<std::string> excluded_directories = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
        ".idea",
        ".vscode"
    };
};

struct IndexedFile {
    std::string path;
    std::string extension;
    std::string content;

    std::uint64_t content_hash = 0;
    std::uintmax_t size_bytes = 0;

    std::size_t line_count = 0;

    bool binary = false;
};

struct IndexingError {
    std::string path;
    std::string message;
};

struct IndexingResult {
    std::size_t discovered_count = 0;
    std::size_t indexed_count = 0;
    std::size_t updated_count = 0;
    std::size_t unchanged_count = 0;
    std::size_t skipped_count = 0;
    std::size_t removed_count = 0;

    bool success = true;

    std::vector<IndexingError> errors;
};

class RepositoryIndexer {
public:
    RepositoryIndexer() = default;

    [[nodiscard]]
    IndexingResult index_directory(
        const std::filesystem::path& root,
        const IndexOptions& options = {}
    );

    [[nodiscard]]
    std::optional<IndexedFile> index_file(
        const std::filesystem::path& file,
        const std::filesystem::path& root,
        std::size_t max_file_size_bytes =
            2 * 1024 * 1024
    );

    [[nodiscard]]
    bool remove_file(std::string_view relative_path);

    void clear();

    [[nodiscard]]
    std::optional<IndexedFile> get_file(
        std::string_view relative_path
    ) const;

    [[nodiscard]]
    std::vector<IndexedFile> get_all_files() const;

    [[nodiscard]]
    std::vector<IndexedFile> search_content(
        std::string_view query,
        bool case_sensitive = true,
        std::size_t max_results = 1000
    ) const;

    [[nodiscard]]
    std::size_t file_count() const noexcept;

private:
    std::unordered_map<std::string, IndexedFile> files_;

    [[nodiscard]]
    static std::string normalize_path(
        const std::filesystem::path& path
    );

    [[nodiscard]]
    static bool is_hidden(
        const std::filesystem::path& path
    );

    [[nodiscard]]
    static bool is_excluded_directory(
        const std::filesystem::path& path,
        const IndexOptions& options
    );

    [[nodiscard]]
    static bool is_allowed_extension(
        const std::filesystem::path& path,
        const IndexOptions& options
    );

    [[nodiscard]]
    static std::size_t count_lines(
        std::string_view content
    );

    [[nodiscard]]
    static std::string normalize_case(
        std::string_view value,
        bool case_sensitive
    );

    [[nodiscard]]
    static std::optional<IndexedFile> read_and_index(
        const std::filesystem::path& file,
        const std::filesystem::path& root,
        std::size_t max_file_size_bytes
    );
};

} // namespace forgex::indexing
