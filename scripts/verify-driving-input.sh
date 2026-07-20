#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
devices="keyboard,controller"
profiles="all"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --devices)
      devices="${2:-}"
      shift 2
      ;;
    --devices=*)
      devices="${1#--devices=}"
      shift
      ;;
    --profiles)
      profiles="${2:-}"
      shift 2
      ;;
    --profiles=*)
      profiles="${1#--profiles=}"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

validate_scope() {
  local scope_name="$1"
  local requested="$2"
  shift 2
  local allowed=("$@")
  local values=()
  IFS=',' read -r -a values <<< "$requested"
  if [[ ${#values[@]} -eq 0 || -z "$requested" ]]; then
    echo "$scope_name scope must not be empty" >&2
    exit 2
  fi
  local seen="," value candidate matched
  for value in "${values[@]}"; do
    matched=0
    for candidate in "${allowed[@]}"; do
      if [[ "$value" == "$candidate" ]]; then
        matched=1
        break
      fi
    done
    if [[ $matched -eq 0 || "$seen" == *",$value,"* ]]; then
      echo "Invalid $scope_name scope: $requested" >&2
      exit 2
    fi
    seen+="$value,"
  done
}

validate_scope "device" "$devices" keyboard controller
if [[ "$profiles" == "all" ]]; then
  requested_profiles=(accessible balanced raw)
else
  validate_scope "profile" "$profiles" accessible balanced raw
  IFS=',' read -r -a requested_profiles <<< "$profiles"
fi

contains_scope() {
  [[ ",$1," == *",$2,"* ]]
}

dotnet_filter='FullyQualifiedName~DrivingInputConditionerTests'
if contains_scope "$devices" keyboard && ! contains_scope "$devices" controller; then
  dotnet_filter+='&FullyQualifiedName~Keyboard'
elif contains_scope "$devices" controller && ! contains_scope "$devices" keyboard; then
  dotnet_filter+='&FullyQualifiedName~Controller'
fi

if [[ "$profiles" != "all" ]]; then
  profile_terms=()
  for profile in "${requested_profiles[@]}"; do
    case "$profile" in
      accessible) profile_terms+=("DisplayName~Accessible") ;;
      balanced) profile_terms+=("DisplayName~Balanced") ;;
      raw) profile_terms+=("DisplayName~Raw") ;;
    esac
  done
  profile_expression="$(IFS='|'; echo "${profile_terms[*]}")"
  dotnet_filter+="&($profile_expression)"
fi

if contains_scope "$devices" keyboard && contains_scope "$devices" controller; then
  playgodot_filter='test_driving_input'
elif contains_scope "$devices" keyboard; then
  playgodot_filter='test_keyboard or test_pause or test_stationary'
else
  playgodot_filter='test_controller'
fi

cd "$repo_root"
export CANNONBALL_DRIVING_DEVICES="$devices"
export CANNONBALL_DRIVING_PROFILES="$profiles"
DOTNET_ROLL_FORWARD=Major dotnet test Cannonball.sln --nologo \
  --filter "$dotnet_filter"
"$repo_root/scripts/verify-playgodot.sh" --test-filter "$playgodot_filter"
