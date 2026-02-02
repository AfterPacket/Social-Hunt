# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

-   Social-Hunt API prefix moved to `/sh-api` to allow IOPaint to run under `/iopaint`.
-   Apache example config for `/iopaint` + `/sh-api`, including ModSecurity exception and upload limits.
-   Git ignore rule for local `_backup_*/` folders.
-   Nginx reverse proxy guide and docker-compose optional IOPaint service.
-   Canary warrant template, PGP key placeholder, and OSINT news digest template.

## [2.2.0"] - 2026-01-27

### Security

-   **Resolved Critical Security Vulnerabilities and Dependency Conflicts**

    A series of critical updates have been made to the project's dependencies to address several security vulnerabilities and to resolve dependency conflicts that were affecting the project's stability.

    #### Vulnerability Fixes

    1.  **`protobuf` - Denial of Service (DoS) Vulnerability (`CVE-2024-5634`)**
        -   A denial-of-service vulnerability was discovered in the `protobuf` library, where a specially crafted message could cause a crash due to a JSON recursion depth bypass.
        -   The `protobuf` dependency has been updated to version `7.34.0rc1`, which contains a fix for this issue.

    2.  **`starlette` - Denial of Service (DoS) Vulnerability (`CVE-2024-37290`)**
        -   A denial-of-service vulnerability was discovered in `starlette`'s `FileResponse` handling of the HTTP `Range` header. A malicious actor could send a crafted `Range` header, causing the server to enter a long-running process and become unresponsive.
        -   The `starlette` dependency has been updated to version `0.49.1`, and `fastapi` has been updated to `0.128.0` to ensure compatibility with the patched version of `starlette`.

    3.  **`esptool` - Security Vulnerability (`PYSEC-2023-234`)**
        -   A security vulnerability was identified in the `esptool` package.
        -   The `esptool` dependency has been added to the project and updated to the latest version (`5.1.0`). Please note that at the time of this update, a full patch for this vulnerability has not yet been released by the package maintainers. We will continue to monitor the package for future updates.

    #### Dependency Conflict Resolutions

    1.  **`numpy` Version Incompatibility**
        -   The version of `numpy` previously specified was not compatible with the Python version used in the development environment, causing installation errors.
        -   The `numpy` dependency has been pinned to version `2.2.6` to ensure compatibility.

    2.  **`xformers` and `torch` Conflict**
        -   The `xformers` package had a strict dependency on an older version of `torch`, which conflicted with the version required by the project.
        -   The `xformers` package was upgraded to the latest version (`0.0.34`), which is compatible with the version of `torch` used in our project.
