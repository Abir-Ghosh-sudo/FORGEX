
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl/filesystem.h>

#include "../core/core.hpp"
#include "../parser/parser.hpp"
#include "../search/search.hpp"
#include "../indexing/indexing.hpp"
#include "../indexing/index_store.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_native, module) {

    module.doc() =
        "FORGEX native C++ engine bindings";

    // -------------------------------------------------
    // Core
    // -------------------------------------------------

    py::class_<forgex::core::EngineInfo>(
        module,
        "EngineInfo"
    )
        .def_readonly("name", &forgex::core::EngineInfo::name)
        .def_readonly("version", &forgex::core::EngineInfo::version)
        .def_readonly("platform", &forgex::core::EngineInfo::platform)
        .def_readonly("compiler", &forgex::core::EngineInfo::compiler)
        .def_readonly("cpp_standard", &forgex::core::EngineInfo::cpp_standard);

    py::class_<forgex::core::TextStatistics>(
        module,
        "TextStatistics"
    )
        .def_readonly("characters", &forgex::core::TextStatistics::characters)
        .def_readonly("words", &forgex::core::TextStatistics::words)
        .def_readonly("lines", &forgex::core::TextStatistics::lines)
        .def_readonly("bytes", &forgex::core::TextStatistics::bytes)
        .def_readonly("empty", &forgex::core::TextStatistics::empty);

    py::class_<forgex::core::CoreEngine>(
        module,
        "CoreEngine"
    )
        .def(py::init<>())
        .def_static("get_info", &forgex::core::CoreEngine::get_info)
        .def_static("version", &forgex::core::CoreEngine::version)
        .def_static("platform", &forgex::core::CoreEngine::platform)
        .def_static("compiler", &forgex::core::CoreEngine::compiler)
        .def_static("normalize_whitespace",
            &forgex::core::CoreEngine::normalize_whitespace)
        .def_static("analyze_text",
            &forgex::core::CoreEngine::analyze_text)
        .def_static("is_binary_data",
            &forgex::core::CoreEngine::is_binary_data)
        .def_static("hash_string",
            &forgex::core::CoreEngine::hash_string)
        .def_static("to_lower",
            &forgex::core::CoreEngine::to_lower)
        .def_static("trim",
            &forgex::core::CoreEngine::trim);

    // -------------------------------------------------
    // Parser
    // -------------------------------------------------

    py::enum_<forgex::parser::TokenType>(
        module,
        "TokenType"
    )
        .value("IDENTIFIER", forgex::parser::TokenType::IDENTIFIER)
        .value("KEYWORD", forgex::parser::TokenType::KEYWORD)
        .value("NUMBER", forgex::parser::TokenType::NUMBER)
        .value("STRING", forgex::parser::TokenType::STRING)
        .value("CHARACTER", forgex::parser::TokenType::CHARACTER)
        .value("OPERATOR", forgex::parser::TokenType::OPERATOR)
        .value("PUNCTUATION", forgex::parser::TokenType::PUNCTUATION)
        .value("COMMENT", forgex::parser::TokenType::COMMENT)
        .value("WHITESPACE", forgex::parser::TokenType::WHITESPACE)
        .value("UNKNOWN", forgex::parser::TokenType::UNKNOWN);

    py::class_<forgex::parser::Token>(
        module,
        "Token"
    )
        .def_readonly("type", &forgex::parser::Token::type)
        .def_readonly("value", &forgex::parser::Token::value)
        .def_readonly("start", &forgex::parser::Token::start)
        .def_readonly("end", &forgex::parser::Token::end)
        .def_readonly("line", &forgex::parser::Token::line)
        .def_readonly("column", &forgex::parser::Token::column);

    py::class_<forgex::parser::ParseError>(
        module,
        "ParseError"
    )
        .def_readonly("message", &forgex::parser::ParseError::message)
        .def_readonly("position", &forgex::parser::ParseError::position)
        .def_readonly("line", &forgex::parser::ParseError::line)
        .def_readonly("column", &forgex::parser::ParseError::column);

    py::class_<forgex::parser::ParseResult>(
        module,
        "ParseResult"
    )
        .def_readonly("language", &forgex::parser::ParseResult::language)
        .def_readonly("tokens", &forgex::parser::ParseResult::tokens)
        .def_readonly("errors", &forgex::parser::ParseResult::errors)
        .def_readonly("lines", &forgex::parser::ParseResult::lines)
        .def_readonly("success", &forgex::parser::ParseResult::success);

    py::class_<forgex::parser::SourceParser>(
        module,
        "SourceParser"
    )
        .def(py::init<>())
        .def("parse", &forgex::parser::SourceParser::parse)
        .def("tokenize", &forgex::parser::SourceParser::tokenize);

    // -------------------------------------------------
    // Search
    // -------------------------------------------------

    py::class_<forgex::search::SearchOptions>(
        module,
        "SearchOptions"
    )
        .def(py::init<>())
        .def_readwrite(
            "case_sensitive",
            &forgex::search::SearchOptions::case_sensitive
        )
        .def_readwrite(
            "whole_word",
            &forgex::search::SearchOptions::whole_word
        )
        .def_readwrite(
            "use_regex",
            &forgex::search::SearchOptions::use_regex
        )
        .def_readwrite(
            "include_empty_lines",
            &forgex::search::SearchOptions::include_empty_lines
        )
        .def_readwrite(
            "max_results",
            &forgex::search::SearchOptions::max_results
        );

    py::class_<forgex::search::SearchMatch>(
        module,
        "SearchMatch"
    )
        .def_readonly("file_path", &forgex::search::SearchMatch::file_path)
        .def_readonly("matched_text", &forgex::search::SearchMatch::matched_text)
        .def_readonly("line", &forgex::search::SearchMatch::line)
        .def_readonly("column", &forgex::search::SearchMatch::column)
        .def_readonly("start_offset", &forgex::search::SearchMatch::start_offset)
        .def_readonly("end_offset", &forgex::search::SearchMatch::end_offset);

    py::class_<forgex::search::SearchResult>(
        module,
        "SearchResult"
    )
        .def_readonly("query", &forgex::search::SearchResult::query)
        .def_readonly("matches", &forgex::search::SearchResult::matches)
        .def_readonly("total_matches", &forgex::search::SearchResult::total_matches)
        .def_readonly("lines_scanned", &forgex::search::SearchResult::lines_scanned)
        .def_readonly("bytes_scanned", &forgex::search::SearchResult::bytes_scanned)
        .def_readonly("truncated", &forgex::search::SearchResult::truncated)
        .def_readonly("success", &forgex::search::SearchResult::success)
        .def_readonly("error", &forgex::search::SearchResult::error);

    py::class_<forgex::search::CodeSearchEngine>(
        module,
        "CodeSearchEngine"
    )
        .def(py::init<>())
        .def(
            "search_text",
            &forgex::search::CodeSearchEngine::search_text,
            py::arg("content"),
            py::arg("query"),
            py::arg("options") = forgex::search::SearchOptions{},
            py::arg("file_path") = ""
        )
        .def(
            "search_regex",
            &forgex::search::CodeSearchEngine::search_regex,
            py::arg("content"),
            py::arg("pattern"),
            py::arg("options") = forgex::search::SearchOptions{},
            py::arg("file_path") = ""
        )
        .def_static(
            "contains",
            &forgex::search::CodeSearchEngine::contains,
            py::arg("content"),
            py::arg("query"),
            py::arg("case_sensitive") = true
        );

    // -------------------------------------------------
    // Indexing
    // -------------------------------------------------

    py::class_<forgex::indexing::IndexOptions>(
        module,
        "IndexOptions"
    )
        .def(py::init<>())
        .def_readwrite(
            "max_file_size_bytes",
            &forgex::indexing::IndexOptions::max_file_size_bytes
        )
        .def_readwrite(
            "max_files",
            &forgex::indexing::IndexOptions::max_files
        )
        .def_readwrite(
            "include_hidden",
            &forgex::indexing::IndexOptions::include_hidden
        )
        .def_readwrite(
            "remove_missing_files",
            &forgex::indexing::IndexOptions::remove_missing_files
        )
        .def_readwrite(
            "extensions",
            &forgex::indexing::IndexOptions::extensions
        )
        .def_readwrite(
            "excluded_directories",
            &forgex::indexing::IndexOptions::excluded_directories
        );

    py::class_<forgex::indexing::IndexedFile>(
        module,
        "IndexedFile"
    )
        .def_readonly("path", &forgex::indexing::IndexedFile::path)
        .def_readonly("extension", &forgex::indexing::IndexedFile::extension)
        .def_readonly("content", &forgex::indexing::IndexedFile::content)
        .def_readonly("content_hash", &forgex::indexing::IndexedFile::content_hash)
        .def_readonly("size_bytes", &forgex::indexing::IndexedFile::size_bytes)
        .def_readonly("line_count", &forgex::indexing::IndexedFile::line_count)
        .def_readonly("binary", &forgex::indexing::IndexedFile::binary);

    py::class_<forgex::indexing::IndexingError>(
        module,
        "IndexingError"
    )
        .def_readonly("path", &forgex::indexing::IndexingError::path)
        .def_readonly("message", &forgex::indexing::IndexingError::message);

    py::class_<forgex::indexing::IndexingResult>(
        module,
        "IndexingResult"
    )
        .def_readonly("discovered_count", &forgex::indexing::IndexingResult::discovered_count)
        .def_readonly("indexed_count", &forgex::indexing::IndexingResult::indexed_count)
        .def_readonly("updated_count", &forgex::indexing::IndexingResult::updated_count)
        .def_readonly("unchanged_count", &forgex::indexing::IndexingResult::unchanged_count)
        .def_readonly("skipped_count", &forgex::indexing::IndexingResult::skipped_count)
        .def_readonly("removed_count", &forgex::indexing::IndexingResult::removed_count)
        .def_readonly("success", &forgex::indexing::IndexingResult::success)
        .def_readonly("errors", &forgex::indexing::IndexingResult::errors);

    py::class_<forgex::indexing::RepositoryIndexer>(
        module,
        "RepositoryIndexer"
    )
        .def(py::init<>())
        .def(
            "index_directory",
            &forgex::indexing::RepositoryIndexer::index_directory,
            py::arg("root"),
            py::arg("options") = forgex::indexing::IndexOptions{}
        )
        .def(
            "index_file",
            &forgex::indexing::RepositoryIndexer::index_file,
            py::arg("file"),
            py::arg("root"),
            py::arg("max_file_size_bytes") = 2 * 1024 * 1024
        )
        .def("remove_file", &forgex::indexing::RepositoryIndexer::remove_file)
        .def("clear", &forgex::indexing::RepositoryIndexer::clear)
        .def("get_file", &forgex::indexing::RepositoryIndexer::get_file)
        .def("get_all_files", &forgex::indexing::RepositoryIndexer::get_all_files)
        .def("search_content", &forgex::indexing::RepositoryIndexer::search_content,
            py::arg("query"),
            py::arg("case_sensitive") = true,
            py::arg("max_results") = 1000)
        .def("file_count", &forgex::indexing::RepositoryIndexer::file_count);

    py::class_<forgex::indexing::IndexStore>(
        module,
        "IndexStore"
    )
        .def(py::init<std::filesystem::path>())
        .def("save", &forgex::indexing::IndexStore::save)
        .def("load", &forgex::indexing::IndexStore::load)
        .def("clear", &forgex::indexing::IndexStore::clear)
        .def_property_readonly(
            "storage_path",
            &forgex::indexing::IndexStore::storage_path
        );

    module.def(
        "native_capabilities",
        []() {
            py::dict capabilities;

            capabilities["core"] = true;
            capabilities["parser"] = true;
            capabilities["search"] = true;
            capabilities["indexing"] = true;
            capabilities["persistent_index"] = true;

            return capabilities;
        }
    );
}
