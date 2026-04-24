#ifndef WEB_SERVER_ADAPTER_H
#define WEB_SERVER_ADAPTER_H

#include "IWebServer.h"
#include <WebServer.h>
#include <functional>
#include <map>
#include <string>

// Adapter that wraps the real WebServer
class WebServerAdapter : public IWebServer {
public:
    WebServerAdapter(int port) : _server(port) {}

    void on(const char* uri, std::function<void()> handler) override {
        _server.on(uri, HTTP_GET, handler);
    }

    void onPost(const char* uri, std::function<void()> handler) override {
        _server.on(uri, HTTP_POST, handler);
    }

    void onNotFound(std::function<void()> handler) override {
        _server.onNotFound(handler);
    }

    void begin() override {
        _server.begin();
    }

    void stop() override {
        _server.stop();
    }

    void handleClient() override {
        _server.handleClient();
    }

    bool hasArg(const char* name) override {
        return _server.hasArg(name);
    }

    const char* arg(const char* name) override {
        _argBuffers[name] = _server.arg(name);
        return _argBuffers[name].c_str();
    }

    const char* uri() override {
        _uriBuffer = _server.uri();
        return _uriBuffer.c_str();
    }

    void send(int code, const char* content_type, const char* content) override {
        _server.send(code, content_type, content);
    }

private:
    WebServer _server;
    std::map<std::string, String> _argBuffers;
    String _uriBuffer;
};

#endif // WEB_SERVER_ADAPTER_H
