
#include "index_store.hpp"

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <system_error>

namespace forgex::indexing {

namespace {

constexpr char MAGIC[] = "FGIDX001";
constexpr std::uint64_t MAX_FILE_COUNT = 1000000;
constexpr std::uint64_t MAX_STRING_SIZE = 64ULL * 1024 * 1024;

template <typename T>
bool write_value(std::ofstream& stream, const T& value) {
    stream.write(
        reinterpret_cast<const char*>(&value),
        sizeof(T)
    );

    return static_cast<bool>(stream);
}

template <typename T>
bool read_value(std::ifstream& stream, T& value) {
    stream.read(
        reinterpret_cast<char*>(&value),
        sizeof(T)
    );

    return static_cast<bool>(stream);
}

bool write_string(
    std::ofstream& stream,
    const std::string& value
) {
    const auto size =
        static_cast<std::uint64_t>(value.size());

    if (size > MAX_STRING_SIZE) {
        return false;
    }

    return write_value(stream, size) &&
           (
               value.empty() ||
               static_cast<bool>(
                   stream.write(value.data(), value.size())
               )
           );
}

bool read_string(
    std::ifstream& stream,
    std::string& value
) {
    std::uint64_t size = 0;

    if (!read_value(stream, size) || size > MAX_STRING_SIZE) {
        return false;
    }

    value.resize(static_cast<std::size_t>(size));

    if (size > 0) {
        stream.read(
            value.data(),
            static_cast<std::streamsize>(size)
        );
    }

    return static_cast<bool>(stream);
}

} // namespace

IndexStore::IndexStore(
    std::filesystem::path storage_directory
)
    : storage_directory_(std::move(storage_directory)),
      storage_file_(storage_directory_ / "forgex.index") {
}

bool IndexStore::save(
    const std::vector<IndexedFile>& files
) const {
    std::error_code error;

    std::filesystem::create_directories(
        storage_directory_,
        error
    );

    if (error) {
        return false;
    }

    const auto temporary_file =
        storage_file_.string() + ".tmp";

    std::ofstream stream(
        temporary_file,
        std::ios::binary | std::ios::trunc
    );

    if (!stream) {
        return false;
    }

    stream.write(MAGIC, sizeof(MAGIC) - 1);

    const auto count =
        static_cast<std::uint64_t>(files.size());

    if (
        !stream ||
        count > MAX_FILE_COUNT ||
        !write_value(stream, count)
    ) {
        stream.close();
        std::filesystem::remove(temporary_file, error);
        return false;
    }

    for (const IndexedFile& file : files) {
        const std::uint8_t binary =
            file.binary ? 1 : 0;

        if (
            !write_string(stream, file.path) ||
            !write_string(stream, file.extension) ||
            !write_string(stream, file.content) ||
            !write_value(stream, file.content_hash) ||
            !write_value(stream, file.size_bytes) ||
            !write_value(stream, file.line_count) ||
            !write_value(stream, binary)
        ) {
            stream.close();
            std::filesystem::remove(temporary_file, error);
            return false;
        }
    }

    stream.flush();

    if (!stream) {
        stream.close();
        std::filesystem::remove(temporary_file, error);
        return false;
    }

    stream.close();

    std::filesystem::rename(
        temporary_file,
        storage_file_,
        error
    );

    if (error) {
        // Windows may not replace an existing destination.
        error.clear();

        std::filesystem::remove(storage_file_, error);
        error.clear();

        std::filesystem::rename(
            temporary_file,
            storage_file_,
            error
        );
    }

    if (error) {
        std::filesystem::remove(temporary_file, error);
        return false;
    }

    return true;
}

std::optional<std::vector<IndexedFile>> IndexStore::load() const {
    std::ifstream stream(
        storage_file_,
        std::ios::binary
    );

    if (!stream) {
        return std::nullopt;
    }

    char magic[sizeof(MAGIC) - 1] = {};

    stream.read(magic, sizeof(magic));

    if (
        !stream ||
        std::string(magic, sizeof(magic)) !=
            std::string(MAGIC, sizeof(MAGIC) - 1)
    ) {
        return std::nullopt;
    }

    std::uint64_t count = 0;

    if (
        !read_value(stream, count) ||
        count > MAX_FILE_COUNT
    ) {
        return std::nullopt;
    }

    std::vector<IndexedFile> files;

    files.reserve(static_cast<std::size_t>(count));

    for (std::uint64_t index = 0; index < count; ++index) {
        IndexedFile file;
        std::uint8_t binary = 0;

        if (
            !read_string(stream, file.path) ||
            !read_string(stream, file.extension) ||
            !read_string(stream, file.content) ||
            !read_value(stream, file.content_hash) ||
            !read_value(stream, file.size_bytes) ||
            !read_value(stream, file.line_count) ||
            !read_value(stream, binary) ||
            binary > 1
        ) {
            return std::nullopt;
        }

        file.binary = binary != 0;

        files.push_back(std::move(file));
    }

    // Reject truncated or unexpectedly extended index files.
    if (stream.peek() != std::ifstream::traits_type::eof()) {
        return std::nullopt;
    }

    return files;
}

bool IndexStore::clear() const {
    std::error_code error;

    const bool removed =
        std::filesystem::remove(storage_file_, error);

    return !error && (removed || !std::filesystem::exists(storage_file_));
}

const std::filesystem::path& IndexStore::storage_path() const noexcept {
    return storage_file_;
}

} // namespace forgex::indexing
