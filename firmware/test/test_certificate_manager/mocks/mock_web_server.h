#ifndef MOCK_WEB_SERVER_H
#define MOCK_WEB_SERVER_H

#include "../../../lib/CertificateManager/include/IWebServer.h"
#include <functional>
#include <map>
#include <string>

class MockWebServer : public IWebServer {
public:
    MockWebServer() : beginCalled(false), stopCalled(false), handleClientCallCount(0) {}

    void on(const char* uri, std::function<void()> handler) override {
        handlers[std::string(uri)] = handler;
    }

    void onPost(const char* uri, std::function<void()> handler) override {
        handlers[std::string(uri)] = handler;
    }

    void onNotFound(std::function<void()> handler) override {
        notFoundHandler = handler;
    }

    void begin() override {
        beginCalled = true;
    }

    void stop() override {
        stopCalled = true;
    }

    void handleClient() override {
        handleClientCallCount++;
    }

    bool hasArg(const char* name) override {
        return args.find(std::string(name)) != args.end();
    }

    const char* arg(const char* name) override {
        auto it = args.find(std::string(name));
        if (it != args.end()) {
            return it->second.c_str();
        }
        return "";
    }

    const char* uri() override {
        return currentUri.c_str();
    }

    void send(int code, const char* content_type, const char* content) override {
        lastResponseCode = code;
        lastContentType = std::string(content_type);
        lastResponse = std::string(content);
    }

    // Test helpers
    void setArg(const char* name, const char* value) {
        args[std::string(name)] = std::string(value);
    }

    void clearArgs() {
        args.clear();
    }

    void triggerHandler(const char* uri) {
        currentUri = std::string(uri);
        auto it = handlers.find(currentUri);
        if (it != handlers.end()) {
            it->second();
        } else if (notFoundHandler) {
            notFoundHandler();
        }
    }

    void reset() {
        handlers.clear();
        args.clear();
        beginCalled = false;
        stopCalled = false;
        handleClientCallCount = 0;
        lastResponseCode = 0;
        lastContentType = "";
        lastResponse = "";
        currentUri = "";
    }

    bool beginCalled;
    bool stopCalled;
    int handleClientCallCount;
    int lastResponseCode;
    std::string lastContentType;
    std::string lastResponse;

private:
    std::map<std::string, std::function<void()>> handlers;
    std::function<void()> notFoundHandler;
    std::map<std::string, std::string> args;
    std::string currentUri;
};

#endif // MOCK_WEB_SERVER_H
