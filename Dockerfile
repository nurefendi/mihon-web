FROM golang:1.27.4-alpine@sha256:70bd7ddea8b6cbe5d6943cde279d6b67feb10cc924fb9100d1d8757c1575b280 AS build
WORKDIR /src
ENV CGO_ENABLED=0 GOMAXPROCS=2
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build go test -p 1 ./... && go vet ./... && go build -trimpath -ldflags='-s -w' -o /out/mihon-web .
FROM alpine:3.23@sha256:85fe1e81d6758c208f3e1eed4338a1997e19d4be002d4dd32d3100c9a8c010a0
RUN apk add --no-cache ca-certificates && addgroup -g 10001 app && adduser -D -u 10001 -G app app
COPY --from=build /out/mihon-web /usr/local/bin/mihon-web
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/mihon-web"]
