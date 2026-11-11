
#include "parser.hpp"

#include <algorithm>
#include <cctype>
#include <string>
#include <string_view>
#include <unordered_set>

namespace forgex::parser {

namespace {

using KeywordSet = std::unordered_set<std::string>;

const KeywordSet COMMON_KEYWORDS = {
    "if", "else", "for", "while", "do",
    "switch", "case", "break", "continue",
    "return", "try", "catch", "throw",
    "class", "struct", "enum", "public",
    "private", "protected", "static",
    "const", "void", "int", "float",
    "double", "char", "bool", "true",
    "false", "null", "nullptr", "new",
    "delete", "this", "namespace", "using"
};

const KeywordSet PYTHON_KEYWORDS = {
    "False", "None", "True", "and", "as",
    "assert", "async", "await", "class",
    "continue", "def", "del", "elif",
    "else", "except", "finally", "for",
    "from", "global", "if", "import",
    "in", "is", "lambda", "nonlocal",
    "not", "or", "pass", "raise",
    "return", "try", "while", "with",
    "yield"
};

const KeywordSet JAVASCRIPT_KEYWORDS = {
    "async", "await", "break", "case",
    "catch", "class", "const", "continue",
    "debugger", "default", "delete", "do",
    "else", "export", "extends", "finally",
    "for", "from", "function", "if",
    "import", "in", "instanceof", "let",
    "new", "of", "return", "static",
    "super", "switch", "this", "throw",
    "try", "typeof", "var", "void",
    "while", "with", "yield"
};

const KeywordSet RUST_KEYWORDS = {
    "as", "async", "await", "break",
    "const", "continue", "crate", "else",
    "enum", "extern", "false", "fn",
    "for", "if", "impl", "in", "let",
    "loop", "match", "mod", "move",
    "mut", "pub", "ref", "return",
    "self", "Self", "static", "struct",
    "super", "trait", "true", "type",
    "unsafe", "use", "where", "while"
};

std::string normalize_language(std::string_view language) {
    std::string result(language);

    std::transform(
        result.begin(),
        result.end(),
        result.begin(),
        [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        }
    );

    return result;
}

bool is_python(std::string_view language) {
    return language == "python" || language == "py";
}

bool is_hash_comment_language(std::string_view language) {
    return is_python(language) ||
           language == "ruby" ||
           language == "bash" ||
           language == "shell" ||
           language == "sh" ||
           language == "yaml";
}

bool is_slash_comment_language(std::string_view language) {
    return !(
        language == "html" ||
        language == "xml" ||
        language == "css"
    );
}

} // namespace

bool SourceParser::is_identifier_start(char character) {
    const unsigned char c =
        static_cast<unsigned char>(character);

    return std::isalpha(c) ||
           character == '_' ||
           c >= 128;
}

bool SourceParser::is_identifier_part(char character) {
    const unsigned char c =
        static_cast<unsigned char>(character);

    return std::isalnum(c) ||
           character == '_' ||
           c >= 128;
}

bool SourceParser::is_operator_start(char character) {
    constexpr std::string_view operators =
        "+-*/%=!<>&|^~?:";

    return operators.find(character) !=
           std::string_view::npos;
}

bool SourceParser::is_punctuation(char character) {
    constexpr std::string_view punctuation =
        "(){}[];,#.";

    return punctuation.find(character) !=
           std::string_view::npos;
}

bool SourceParser::is_keyword(
    std::string_view value,
    std::string_view language
) {
    const std::string keyword(value);

    if (is_python(language)) {
        return PYTHON_KEYWORDS.find(keyword) !=
               PYTHON_KEYWORDS.end();
    }

    if (
        language == "javascript" ||
        language == "typescript" ||
        language == "js" ||
        language == "ts"
    ) {
        return JAVASCRIPT_KEYWORDS.find(keyword) !=
               JAVASCRIPT_KEYWORDS.end();
    }

    if (language == "rust" || language == "rs") {
        return RUST_KEYWORDS.find(keyword) !=
               RUST_KEYWORDS.end();
    }

    return COMMON_KEYWORDS.find(keyword) !=
           COMMON_KEYWORDS.end();
}

std::vector<Token> SourceParser::tokenize(
    std::string_view source,
    std::string_view language
) const {
    std::vector<Token> tokens;

    const std::string lang =
        normalize_language(language);

    std::size_t position = 0;
    std::size_t line = 1;
    std::size_t column = 1;

    auto advance = [&](char character) {
        ++position;

        if (character == '\n') {
            ++line;
            column = 1;
        } else {
            ++column;
        }
    };

    auto emit = [&](
        TokenType type,
        std::size_t start,
        std::size_t start_line,
        std::size_t start_column
    ) {
        tokens.push_back(Token{
            type,
            std::string(
                source.substr(start, position - start)
            ),
            start,
            position,
            start_line,
            start_column
        });
    };

    while (position < source.size()) {
        const char current = source[position];

        const std::size_t start = position;
        const std::size_t start_line = line;
        const std::size_t start_column = column;

        // Whitespace
        if (std::isspace(
                static_cast<unsigned char>(current)
            )) {

            while (
                position < source.size() &&
                std::isspace(
                    static_cast<unsigned char>(source[position])
                )
            ) {
                advance(source[position]);
            }

            emit(
                TokenType::WHITESPACE,
                start,
                start_line,
                start_column
            );

            continue;
        }

        // Single-line comments
        const bool slash_comment =
            is_slash_comment_language(lang) &&
            current == '/' &&
            position + 1 < source.size() &&
            source[position + 1] == '/';

        const bool hash_comment =
            is_hash_comment_language(lang) &&
            current == '#';

        if (slash_comment || hash_comment) {
            while (
                position < source.size() &&
                source[position] != '\n'
            ) {
                advance(source[position]);
            }

            emit(
                TokenType::COMMENT,
                start,
                start_line,
                start_column
            );

            continue;
        }

        // Block comments
        if (
            current == '/' &&
            position + 1 < source.size() &&
            source[position + 1] == '*' &&
            lang != "python"
        ) {
            advance(source[position]);
            advance(source[position]);

            while (position < source.size()) {
                if (
                    source[position] == '*' &&
                    position + 1 < source.size() &&
                    source[position + 1] == '/'
                ) {
                    advance(source[position]);
                    advance(source[position]);
                    break;
                }

                advance(source[position]);
            }

            emit(
                TokenType::COMMENT,
                start,
                start_line,
                start_column
            );

            continue;
        }

        // String and character literals
        const bool python_prefix =
            is_python(lang) &&
            (
                current == 'f' ||
                current == 'r' ||
                current == 'b' ||
                current == 'u'
            ) &&
            position + 1 < source.size() &&
            (
                source[position + 1] == '"' ||
                source[position + 1] == '\''
            );

        const bool string_start =
            current == '"' ||
            current == '\'' ||
            python_prefix;

        if (string_start) {
            if (python_prefix) {
                advance(source[position]);
            }

            const char quote = source[position];
            const bool character_literal = quote == '\'';

            advance(source[position]);

            while (position < source.size()) {
                const char c = source[position];

                if (c == '\\') {
                    advance(c);

                    if (position < source.size()) {
                        advance(source[position]);
                    }

                    continue;
                }

                if (c == quote) {
                    advance(c);
                    break;
                }

                advance(c);
            }

            emit(
                character_literal
                    ? TokenType::CHARACTER
                    : TokenType::STRING,
                start,
                start_line,
                start_column
            );

            continue;
        }

        // Numbers
        if (std::isdigit(
                static_cast<unsigned char>(current)
            )) {

            advance(current);

            while (position < source.size()) {
                const char c = source[position];

                if (
                    std::isalnum(
                        static_cast<unsigned char>(c)
                    ) ||
                    c == '.' ||
                    c == '_'
                ) {
                    advance(c);
                } else {
                    break;
                }
            }

            emit(
                TokenType::NUMBER,
                start,
                start_line,
                start_column
            );

            continue;
        }

        // Identifiers and keywords
        if (is_identifier_start(current)) {
            advance(current);

            while (
                position < source.size() &&
                is_identifier_part(source[position])
            ) {
                advance(source[position]);
            }

            const std::string_view value =
                source.substr(start, position - start);

            emit(
                is_keyword(value, lang)
                    ? TokenType::KEYWORD
                    : TokenType::IDENTIFIER,
                start,
                start_line,
                start_column
            );

            continue;
        }

        // Operators
        if (is_operator_start(current)) {
            advance(current);

            while (
                position < source.size() &&
                is_operator_start(source[position])
            ) {
                advance(source[position]);
            }

            emit(
                TokenType::OPERATOR,
                start,
                start_line,
                start_column
            );

            continue;
        }

        // Punctuation
        if (is_punctuation(current)) {
            advance(current);

            emit(
                TokenType::PUNCTUATION,
                start,
                start_line,
                start_column
            );

            continue;
        }

        // Unknown character
        advance(current);

        emit(
            TokenType::UNKNOWN,
            start,
            start_line,
            start_column
        );
    }

    return tokens;
}

ParseResult SourceParser::parse(
    std::string_view source,
    std::string_view language
) const {
    ParseResult result;

    result.language = normalize_language(language);
    result.tokens = tokenize(source, result.language);

    result.lines = source.empty()
        ? 0
        : static_cast<std::size_t>(
            std::count(
                source.begin(),
                source.end(),
                '\n'
            )
        ) + (source.back() == '\n' ? 0 : 1);

    for (const Token& token : result.tokens) {
        if (token.type == TokenType::UNKNOWN) {
            result.errors.push_back(ParseError{
                "Unrecognized source character",
                token.start,
                token.line,
                token.column
            });
        }
    }

    result.success = result.errors.empty();

    return result;
}

} // namespace forgex::parser
