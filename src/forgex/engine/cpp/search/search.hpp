#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace forgex::search {

struct SearchOptions {
    bool case_sensitive = true;
    bool whole_word = false;
    bool use_regex = false;
    bool include_empty_lines = false;
    std::size_t max_results = 1000;
};

struct SearchMatch {
    std::string file_path;
    std::string matched_text;
    std::size_t line = 1;
    std::size_t column = 1;
    std::size_t start_offset = 0;
    std::size_t end_offset = 0;
};

struct SearchResult {
    std::string query;
    std::vector<SearchMatch> matches;

    std::size_t total_matches = 0;
    std::size_t lines_scanned = 0;
    std::size_t bytes_scanned = 0;

    bool truncated = false;
    bool success = true;
    std::string error;
};

class CodeSearchEngine {
public:
    [[nodiscard]]
    SearchResult search_text(
        std::string_view content,
        std::string_view query,
        const SearchOptions& options = {},
        std::string_view file_path = {}
    ) const;

    [[nodiscard]]
    SearchResult search_regex(
        std::string_view content,
        std::string_view pattern,
        const SearchOptions& options = {},
        std::string_view file_path = {}
    ) const;

    [[nodiscard]]
    static bool contains(
        std::string_view content,
        std::string_view query,
        bool case_sensitive = true
    );

private:
    [[nodiscard]]
    static bool is_word_character(char character);

    [[nodiscard]]
    static std::string normalize_case(
        std::string_view value,
        bool case_sensitive
    );
};

} // namespace forgex::search