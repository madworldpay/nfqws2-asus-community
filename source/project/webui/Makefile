SHELL := /bin/bash
VERSION := $(shell cat VERSION)
ROOT_DIR := /opt

include repository.mk
include web.mk

.DEFAULT_GOAL := packages

clean:
	rm -rf out/_pages
	rm -rf out/web
