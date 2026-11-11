#include "search.hpp"

#include <algorithm>
#include <cctype>
#include <regex>
#include <string>
#include <string_view>

namespace forgex::search {

std::string CodeSearchEngine::normalize_case(
    std::string_view value,
    bool case_sensitive
) {
    std::string result(value);

    if (!case_sensitive) {
        std::transform(
            result.begin(),
            result.end(),
            result.begin(),
            [](unsigned char character) {
                return static_cast<char>(
                    std::tolower(character)
                );
            }
        );
    }

    return result;
}

bool CodeSearchEngine::is_word_character(char character) {
    const unsigned char c =
        static_cast<unsigned char>(character);

    return std::isalnum(c) || character == '_';
}

bool CodeSearchEngine::contains(
    std::string_view content,
    std::string_view query,
    bool case_sensitive
) {
    if (query.empty()) {
        return false;
    }

    const std::string source =
        normalize_case(content, case_sensitive);

    const std::string target =
        normalize_case(query, case_sensitive);

    return source.find(target) != std::string::npos;
}

SearchResult CodeSearchEngine::search_text(
    std::string_view content,
    std::string_view query,
    const SearchOptions& options,
    std::string_view file_path
) const {
    if (options.use_regex) {
        return search_regex(
            content,
            query,
            options,
            file_path
        );
    }

    SearchResult result;
    result.query = std::string(query);
    result.bytes_scanned = content.size();

    if (query.empty()) {
        result.success = false;
        result.error = "Search query cannot be empty";
        return result;
    }

    const std::string source =
        normalize_case(content, options.case_sensitive);

    const std::string target =
        normalize_case(query, options.case_sensitive);

    std::size_t line = 1;
    std::size_t line_start = 0;

    while (line_start <= content.size()) {
        const std::size_t newline =
            content.find('\n', line_start);

        const std::size_t line_end =
            newline == std::string_view::npos
                ? content.size()
                : newline;

        const std::string_view current_line =
            content.substr(
                line_start,
                line_end - line_start
            );

        ++result.lines_scanned;

        if (
            options.include_empty_lines ||
            !current_line.empty()
        ) {
            std::size_t position = line_start;

            while (position < line_end) {
                const std::size_t found =
                    source.find(target, position);

                if (
                    found == std::string::npos ||
                    found + target.size() > line_end
                ) {
                    break;
                }

                const std::size_t match_end =
                    found + target.size();

                bool valid_word = true;

                if (options.whole_word) {
                    const bool left_boundary =
                        found == line_start ||
                        !is_word_character(content[found - 1]);

                    const bool right_boundary =
                        match_end == line_end ||
                        !is_word_character(content[match_end]);

                    valid_word =
                        left_boundary && right_boundary;
                }

                if (valid_word) {
                    ++result.total_matches;

                    if (
                        options.max_results == 0 ||
                        result.matches.size() < options.max_results
                    ) {
                        result.matches.push_back(SearchMatch{
                            std::string(file_path),
                            std::string(
                                content.substr(found, target.size())
                            ),
                            line,
                            found - line_start + 1,
                            found,
                            match_end
                        });
                    } else {
                        result.truncated = true;
                    }
                }

                // Advance by one to preserve overlapping matches.
                position = found + 1;
            }
        }

        if (newline == std::string_view::npos) {
            break;
        }

        line_start = newline + 1;
        ++line;
    }

    return result;
}

SearchResult CodeSearchEngine::search_regex(
    std::string_view content,
    std::string_view pattern,
    const SearchOptions& options,
    std::string_view file_path
) const {
    SearchResult result;

    result.query = std::string(pattern);
    result.bytes_scanned = content.size();

    if (pattern.empty()) {
        result.success = false;
        result.error = "Regex pattern cannot be empty";
        return result;
    }

    try {
        auto flags = std::regex_constants::ECMAScript;

        if (!options.case_sensitive) {
            flags |= std::regex_constants::icase;
        }

        const std::regex expression(
            std::string(pattern),
            flags
        );

        std::size_t line = 1;
        std::size_t line_start = 0;

        while (line_start <= content.size()) {
            const std::size_t newline =
                content.find('\n', line_start);

            const std::size_t line_end =
                newline == std::string_view::npos
                    ? content.size()
                    : newline;

            const std::string current_line(
                content.substr(
                    line_start,
                    line_end - line_start
                )
            );

            ++result.lines_scanned;

            if (
                options.include_empty_lines ||
                !current_line.empty()
            ) {
                using Iterator = std::string::const_iterator;

                std::match_results<Iterator> match;

                auto search_start = current_line.cbegin();
                const auto search_end = current_line.cend();

                while (
                    search_start != search_end &&
                    std::regex_search(
                        search_start,
                        search_end,
                        match,
                        expression
                    )
                ) {
                    const std::size_t match_offset =
                        static_cast<std::size_t>(
                            std::distance(
                                current_line.cbegin(),
                                search_start
                            )
                        ) +
                        static_cast<std::size_t>(match.position());

                    const std::size_t match_length =
                        static_cast<std::size_t>(match.length());

                    const std::size_t absolute_start =
                        line_start + match_offset;

                    const std::size_t absolute_end =
                        absolute_start + match_length;

                    bool valid_word = true;

                    if (options.whole_word && match_length > 0) {
                        const bool left_boundary =
                            match_offset == 0 ||
                            !is_word_character(
                                current_line[match_offset - 1]
                            );

                        const bool right_boundary =
                            match_offset + match_length >=
                                current_line.size() ||
                            !is_word_character(
                                current_line[
                                    match_offset + match_length
                                ]
                            );

                        valid_word =
                            left_boundary && right_boundary;
                    }

                    if (valid_word) {
                        ++result.total_matches;

                        if (
                            options.max_results == 0 ||
                            result.matches.size() < options.max_results
                        ) {
                            result.matches.push_back(SearchMatch{
                                std::string(file_path),
                                match.str(),
                                line,
                                match_offset + 1,
                                absolute_start,
                                absolute_end
                            });
                        } else {
                            result.truncated = true;
                        }
                    }

                    const auto advance_by =
                        std::max<std::ptrdiff_t>(
                            1,
                            match.position() + match.length()
                        );

                    std::advance(search_start, advance_by);
                }
            }

            if (newline == std::string_view::npos) {
                break;
            }

            line_start = newline + 1;
            ++line;
        }
    } catch (const std::regex_error& exception) {
        result.success = false;
        result.error =
            std::string("Invalid regular expression: ") +
            exception.what();
    }

    return result;
}

} // namespace forgex::search