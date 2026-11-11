#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace forgex::core {

inline constexpr const char* ENGINE_NAME = "FORGEX";
inline constexpr const char* ENGINE_VERSION = "1.0.0";

struct EngineInfo {
    std::string name;
    std::string version;
    std::string platform;
    std::string compiler;
    std::uint32_t cpp_standard;
};

struct TextStatistics {
    std::size_t characters = 0;
    std::size_t words = 0;
    std::size_t lines = 0;
    std::size_t bytes = 0;
    bool empty = true;
};

class CoreEngine {
public:
    CoreEngine() = default;

    [[nodiscard]]
    static EngineInfo get_info();

    [[nodiscard]]
    static std::string version();

    [[nodiscard]]
    static std::string platform();

    [[nodiscard]]
    static std::string compiler();

    [[nodiscard]]
    static std::string normalize_whitespace(
        std::string_view input
    );

    [[nodiscard]]
    static TextStatistics analyze_text(
        std::string_view input
    );

    [[nodiscard]]
    static bool is_binary_data(
        std::string_view input
    );

    [[nodiscard]]
    static std::uint64_t hash_string(
        std::string_view input
    );

    [[nodiscard]]
    static std::string to_lower(
        std::string_view input
    );

    [[nodiscard]]
    static std::string trim(
        std::string_view input
    );
};

} // namespace forgex::core
