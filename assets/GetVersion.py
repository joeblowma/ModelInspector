import pyinstaller_versionfile

pyinstaller_versionfile.create_versionfile_from_input_file(
    output_file="version.txt",
    input_file="./assets/versionTemplate.yml",
)
