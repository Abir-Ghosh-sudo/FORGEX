#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace forgex::parser {

enum class TokenType {
    IDENTIFIER,
    KEYWORD,
    NUMBER,
    STRING,
    CHARACTER,
    OPERATOR,
    PUNCTUATION,
    COMMENT,
    WHITESPACE,
    UNKNOWN
};

struct Token {
    TokenType type = TokenType::UNKNOWN;
    std::string value;
    std::size_t start = 0;
    std::size_t end = 0;
    std::size_t line = 1;
    std::size_t column = 1;
};

struct ParseError {
    std::string message;
    std::size_t position = 0;
    std::size_t line = 1;
    std::size_t column = 1;
};

struct ParseResult {
    std::string language;
    std::vector<Token> tokens;
    std::vector<ParseError> errors;
    std::size_t lines = 0;
    bool success = true;
};

class SourceParser {
public:
    [[nodiscard]]
    ParseResult parse(
        std::string_view source,
        std::string_view language
    ) const;

    [[nodiscard]]
    std::vector<Token> tokenize(
        std::string_view source,
        std::string_view language
    ) const;

private:
    [[nodiscard]]
    static bool is_identifier_start(char character);

    [[nodiscard]]
    static bool is_identifier_part(char character);

    [[nodiscard]]
    static bool is_keyword(
        std::string_view value,
        std::string_view language
    );

    [[nodiscard]]
    static bool is_operator_start(char character);

    [[nodiscard]]
    static bool is_punctuation(char character);
};

} // namespace forgex::parser