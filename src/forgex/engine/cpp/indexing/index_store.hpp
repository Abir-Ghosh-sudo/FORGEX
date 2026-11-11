
#pragma once

#include "indexing.hpp"

#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace forgex::indexing {

class IndexStore {
public:
    explicit IndexStore(std::filesystem::path storage_directory);

    [[nodiscard]]
    bool save(
        const std::vector<IndexedFile>& files
    ) const;

    [[nodiscard]]
    std::optional<std::vector<IndexedFile>> load() const;

    [[nodiscard]]
    bool clear() const;

    [[nodiscard]]
    const std::filesystem::path& storage_path() const noexcept;

private:
    std::filesystem::path storage_directory_;
    std::filesystem::path storage_file_;
};

} // namespace forgex::indexing
