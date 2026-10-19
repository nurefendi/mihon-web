FROM golang:1.26-alpine@sha256:3082400e369fa24d5fc60bca20edab3f6d604e0c5a690ec66b295eff4dd87ade AS build
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
