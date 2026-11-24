#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
destination=${1:-ref}
mkdir -p "$destination"
destination=$(cd "$destination" && pwd)
stage=$(mktemp -d "$destination/.download.XXXXXX")
trap 'rm -rf "$stage"' EXIT
trap 'exit 1' HUP INT TERM

verified() {
    printf '%s  %s\n' "$1" "$2" | sha256sum --check --status
}

download() {
    category=$1
    release=$2
    url=$3
    checksum=$4
    archive="$destination/$category.tar.gz"
    if ! verified "$checksum" "$archive" 2>/dev/null; then
        wget -O "$stage/$category.tar.gz" "$url"
        verified "$checksum" "$stage/$category.tar.gz" || {
            printf 'Checksum mismatch for %s\n' "$url" >&2
            exit 1
        }
        mv "$stage/$category.tar.gz" "$archive"
    fi

    mkdir -p "$destination/$category"
    if [ ! -d "$destination/$category/$release" ]; then
        tar -xf "$archive" -C "$stage" \
            --exclude="$release/xhtml" --exclude="$release/diff-from-*" "$release"
        mv "$stage/$release" "$destination/$category/"
    fi
}

base=https://developer.arm.com/-/cdn-downloads/permalink
download isa_a64 ISA_A64_xml_A_profile-2026-09 \
    "$base/Exploration-Tools-A64-ISA/ISA_A64/ISA_A64_xml_A_profile-2026-09.tar.gz" \
    44cfb89c763c7eea8e59de0ad2221e3c012e6aa77899bd7f1c3e1f24537191d7
download sysreg SysReg_xml_A_profile-2026-09 \
    "$base/Exploration-Tools-Arm-Architecture-System-Registers/SysReg/SysReg_xml_A_profile-2026-09.tar.gz" \
    4b39dc702d0ef324444be5ca7d616a873ea5005a183b9d7be8a07a425225ac9f
