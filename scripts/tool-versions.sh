#!/usr/bin/env bash

# Canonical local and CI toolchain. Keep workflow setup inputs aligned with
# these values; scripts/doctor.sh verifies the tools that actually execute.
# shellcheck disable=SC2034  # This file is sourced by multiple entrypoints.

# Sourcing twice in one shell would re-declare the readonly versions below and
# fail, so entrypoints that source each other stay safe.
if [[ -n "${CANNONBALL_TOOL_VERSIONS_SOURCED:-}" ]]; then
  return 0
fi
CANNONBALL_TOOL_VERSIONS_SOURCED=1

readonly CANNONBALL_DOTNET_SDK_VERSION="10.0.102"
readonly CANNONBALL_GODOT_VERSION="4.7.1.stable.mono.official.a13da4feb"
readonly CANNONBALL_GIT_LFS_VERSION="3.7.1"
readonly CANNONBALL_UV_VERSION="0.9.24"

# Make the uv pin load-bearing rather than coincidental. .tools/uv-pinned/uv is a
# shim that runs the pinned version through uvx, but until it is on PATH every
# script gets whatever uv the machine happens to have installed, and a package
# manager upgrading uv silently changes the toolchain under a green gate. That is
# how uv 0.11.29 came to run against a 0.9.24 pin on 2026-08-14.
#
# Prepending is safe when the shim is absent, and callers that deliberately set
# CANNONBALL_SKIP_UV_PIN keep their own uv.
if [[ -z "${CANNONBALL_SKIP_UV_PIN:-}" ]]; then
  # The shim lives under the ignored .tools/, so it is absent on CI and on a
  # fresh clone. The assignment must not be allowed to fail: a failing command
  # substitution takes its exit status, which under set -e kills the sourcing
  # script before it runs anything.
  _cannonball_uv_pin_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.tools/uv-pinned" 2>/dev/null && pwd)" \
    || _cannonball_uv_pin_dir=""
  if [[ -n "$_cannonball_uv_pin_dir" && -x "$_cannonball_uv_pin_dir/uv" ]]; then
    case ":$PATH:" in
      *":$_cannonball_uv_pin_dir:"*) ;;
      *) PATH="$_cannonball_uv_pin_dir:$PATH" ;;
    esac
    export PATH
  fi
  unset _cannonball_uv_pin_dir
fi
