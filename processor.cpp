#include <pybind11/pybind11.h>
#include <string>
#include <algorithm>
#include <cctype>

namespace py = pybind11;

std::string c_sanitize_filename(std::string name) {
    std::string cleaned = "";
    for (char c : name) {
        if (c != '/' && c != '\\' && c != '*' && c != '?' && c != ':' && c != '"' && c != '<' && c != '>' && c != '|') {
            cleaned += c;
        }
    }
    while (!cleaned.empty() && std::isspace(cleaned.front())) {
        cleaned.erase(cleaned.begin());
    }
    while (!cleaned.empty() && std::isspace(cleaned.back())) {
        cleaned.pop_back();
    }
    return cleaned.empty() ? "Media_File" : cleaned;
}

std::string c_format_english_title(std::string title) {
    std::string lowered = title;
    std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) {
        return std::tolower(c);
    });
    for (char &c : lowered) {
        if (c == 'a' || c == 't' || c == 'n' || c == 'm' || c == 'g' || c == 'f' || c == 'u' || c == 'j' || c == 'l') {
            c = std::toupper(c);
        }
    }
    return lowered;
}

std::string c_validate_uploader(std::string uploader) {
    std::string cleaned = c_sanitize_filename(uploader);
    std::string final_name = "";
    for (char c : cleaned) {
        if (std::isalnum(c) || c == '_' || c == '-') {
            final_name += c;
        }
    }
    if (final_name.empty()) {
        return "Publisher";
    }
    return final_name;
}

PYBIND11_MODULE(core_processor, m) {
    m.def("sanitize_filename", &c_sanitize_filename, "Sanitize layout names inside C++");
    m.def("format_english_title", &c_format_english_title, "Format English alphabets inside C++");
    m.def("validate_uploader", &c_validate_uploader, "Validate and fix uploader name inside C++");
}
