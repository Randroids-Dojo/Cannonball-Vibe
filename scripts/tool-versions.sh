#!/usr/bin/env bash

# Canonical local and CI toolchain. Keep workflow setup inputs aligned with
# these values; scripts/doctor.sh verifies the tools that actually execute.
# shellcheck disable=SC2034  # This file is sourced by multiple entrypoints.
readonly CANNONBALL_DOTNET_SDK_VERSION="10.0.102"
readonly CANNONBALL_GODOT_VERSION="4.7.1.stable.mono.official.a13da4feb"
readonly CANNONBALL_GIT_LFS_VERSION="3.7.1"
readonly CANNONBALL_UV_VERSION="0.9.24"
