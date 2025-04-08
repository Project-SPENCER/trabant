package util

import (
	"archive/zip"
	"embed"
	"io"
	"path/filepath"
	"strings"
)

func AddFileToZip(zw *zip.Writer, fs embed.FS, baseDir, currentPath string) error {
	files, err := fs.ReadDir(currentPath)
	if err != nil {
		return err
	}

	for _, file := range files {
		fullPath := filepath.Join(currentPath, file.Name())
		relativePath := strings.TrimPrefix(fullPath, baseDir+"/")
		// log.Printf("Adding %s to zip as %s", fullPath, relativePath)

		if file.IsDir() {
			zw.Create(relativePath + "/")
			// Recursively add the directory contents, but not the directory itself
			if err := AddFileToZip(zw, fs, baseDir, fullPath); err != nil {
				return err
			}
		} else {
			// Add the file to the zip archive with the relative path
			fileInFs, err := fs.Open(fullPath)
			if err != nil {
				return err
			}
			defer fileInFs.Close()

			zipFileWriter, err := zw.Create(relativePath)
			if err != nil {
				return err
			}

			if _, err := io.Copy(zipFileWriter, fileInFs); err != nil {
				return err
			}
		}
	}

	return nil
}

func ZipFolder(fs embed.FS, folderPath string, zw *zip.Writer) error {
	return AddFileToZip(zw, fs, folderPath, folderPath)
}
