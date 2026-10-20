# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- [PS-4] Add auth, student, physio and api blueprints with their URL prefixes
- [PS-1] Add database models and relationships
- [PS-5] Add user registration, login, logout and session management
- [PS-23] Add lint, format and test scripts and a CI workflow for pull requests
- [PS-24] Add automated Claude PR review job to CI
- [PS-12] Add base layout, styling and appointment form frontend
- [PS-2] Add first database migration and database checks in CI
- [PS-3] Add physio_id to appointments, its migration and an inventory seed command
  - Add Avocoding conventions to CLAUDE.md
- [PS-6] Add physio and shared-resource availability checks for concurrent appointments

### Changed

- [PS-25] Improve Claude PR review prompt with inline comments and allowed tools
