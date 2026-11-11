#include "core.hpp"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <string>
#include <string_view>

namespace forgex::core {

EngineInfo CoreEngine::get_info() {
    return EngineInfo{
        ENGINE_NAME,
        ENGINE_VERSION,
        platform(),
        compiler(),
        202002
    };
}

std::string CoreEngine::version() {
    return ENGINE_VERSION;
}

std::string CoreEngine::platform() {
#if defined(_WIN32)
    return "windows";
#elif defined(__linux__)
    return "linux";
#elif defined(__APPLE__)
    return "macos";
#elif defined(__FreeBSD__)
    return "freebsd";
#else
    return "unknown";
#endif
}

std::string CoreEngine::compiler() {
#if defined(_MSC_VER)
    return "MSVC";
#elif defined(__clang__)
    return "Clang";
#elif defined(__GNUC__)
    return "GCC";
#else
    return "Unknown";
#endif
}

std::string CoreEngine::normalize_whitespace(
    std::string_view input
) {
    std::string result;
    result.reserve(input.size());

    bool previous_whitespace = false;

    for (unsigned char character : input) {
        if (std::isspace(character)) {
            if (!previous_whitespace && !result.empty()) {
                result.push_back(' ');
            }

            previous_whitespace = true;
        } else {
            result.push_back(static_cast<char>(character));
            previous_whitespace = false;
        }
    }

    if (!result.empty() && result.back() == ' ') {
        result.pop_back();
    }

    return result;
}

TextStatistics CoreEngine::analyze_text(
    std::string_view input
) {
    TextStatistics stats;

    stats.bytes = input.size();
    stats.empty = input.empty();

    if (input.empty()) {
        return stats;
    }

    stats.characters = input.size();
    stats.lines = 1;

    bool inside_word = false;

    for (unsigned char character : input) {
        if (character == '\n') {
            ++stats.lines;
        }

        if (std::isspace(character)) {
            inside_word = false;
        } else if (!inside_word) {
            ++stats.words;
            inside_word = true;
        }
    }

    return stats;
}

bool CoreEngine::is_binary_data(
    std::string_view input
) {
    constexpr std::size_t SAMPLE_LIMIT = 8192;

    const std::size_t sample_size = std::min(
        input.size(),
        SAMPLE_LIMIT
    );

    if (sample_size == 0) {
        return false;
    }

    std::size_t suspicious = 0;

    for (std::size_t index = 0; index < sample_size; ++index) {
        const unsigned char character =
            static_cast<unsigned char>(input[index]);

        if (character == 0) {
            return true;
        }

        if (
            character < 32 &&
            character != '\n' &&
            character != '\r' &&
            character != '\t' &&
            character != '\f' &&
            character != '\b'
        ) {
            ++suspicious;
        }
    }

    return suspicious * 100 / sample_size > 10;
}

std::uint64_t CoreEngine::hash_string(
    std::string_view input
) {
    // FNV-1a 64-bit hash.
    constexpr std::uint64_t OFFSET_BASIS =
        14695981039346656037ULL;

    constexpr std::uint64_t PRIME =
        1099511628211ULL;

    std::uint64_t hash = OFFSET_BASIS;

    for (unsigned char character : input) {
        hash ^= character;
        hash *= PRIME;
    }

    return hash;
}

std::string CoreEngine::to_lower(
    std::string_view input
) {
    std::string result(input);

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

    return result;
}

std::string CoreEngine::trim(
    std::string_view input
) {
    std::size_t start = 0;
    std::size_t end = input.size();

    while (
        start < end &&
        std::isspace(
            static_cast<unsigned char>(input[start])
        )
    ) {
        ++start;
    }

    while (
        end > start &&
        std::isspace(
            static_cast<unsigned char>(input[end - 1])
        )
    ) {
        --end;
    }

    return std::string(input.substr(start, end - start));
}

} // namespace forgex::core