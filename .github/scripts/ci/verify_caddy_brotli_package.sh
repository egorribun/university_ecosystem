    release="$(cat /etc/alpine-release)"
    case "$release" in
      3.23.*) ;;
      *) echo "Unexpected Caddy Alpine release: $release" >&2; exit 1 ;;
    esac
    printf "Caddy Alpine release: %s\n" "$release"
    cat /etc/apk/repositories
    apk --no-network --verbose info --exists "brotli-libs=1.2.1-r0"
