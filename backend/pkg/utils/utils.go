package utils

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// EnsureDir creates directory if not exists
func EnsureDir(path string) error {
	return os.MkdirAll(path, os.ModePerm)
}

// FileExists checks if file exists
func FileExists(path string) bool {
	_, err := os.Stat(path)
	return !os.IsNotExist(err)
}

// GenerateOutputPaths generates output folder structure
func GenerateOutputPaths(baseDir, documentID string) (string, string, string) {
	documentDir := filepath.Join(baseDir, documentID)

	markdownDir := filepath.Join(documentDir, "markdown")
	jsonDir := filepath.Join(documentDir, "json")
	imagesDir := filepath.Join(documentDir, "images")

	return markdownDir, jsonDir, imagesDir
}

// SanitizeFilename removes unsafe filename characters
func SanitizeFilename(filename string) string {
	filename = strings.ReplaceAll(filename, " ", "_")
	filename = strings.ReplaceAll(filename, "/", "_")
	filename = strings.ReplaceAll(filename, "\\", "_")
	filename = strings.ReplaceAll(filename, ":", "_")

	return filename
}

// SaveJSON saves struct/map to json file
func SaveJSON(path string, data interface{}) error {
	file, err := os.Create(path)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")

	return encoder.Encode(data)
}

// ReadJSON reads json file into struct
func ReadJSON(path string, target interface{}) error {
	file, err := os.ReadFile(path)
	if err != nil {
		return err
	}

	return json.Unmarshal(file, target)
}

// GetTimestamp returns formatted timestamp
func GetTimestamp() string {
	return time.Now().Format("20060102_150405")
}

// GenerateMarkdownPath creates markdown output path
func GenerateMarkdownPath(baseDir, documentID string) string {
	return filepath.Join(
		baseDir,
		documentID,
		"markdown",
		fmt.Sprintf("%s.md", documentID),
	)
}

// GenerateJSONPath creates json output path
func GenerateJSONPath(baseDir, documentID string) string {
	return filepath.Join(
		baseDir,
		documentID,
		"json",
		fmt.Sprintf("%s.json", documentID),
	)
}