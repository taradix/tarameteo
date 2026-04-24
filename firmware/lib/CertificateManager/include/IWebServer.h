#ifndef I_WEB_SERVER_H
#define I_WEB_SERVER_H

#include <functional>

class IWebServer {
public:
    virtual ~IWebServer() {}
    virtual void on(const char* uri, std::function<void()> handler) = 0;
    virtual void onPost(const char* uri, std::function<void()> handler) = 0;
    virtual void onNotFound(std::function<void()> handler) = 0;
    virtual void begin() = 0;
    virtual void stop() = 0;
    virtual void handleClient() = 0;
    virtual bool hasArg(const char* name) = 0;
    virtual const char* arg(const char* name) = 0;
    virtual const char* uri() = 0;
    virtual void send(int code, const char* content_type, const char* content) = 0;
};

#endif // I_WEB_SERVER_H
