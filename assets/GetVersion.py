import subprocess
import datetime

def get_git_version():
    try:
        # Example output: "1.0-25-g7b4eabd"
        git_version = subprocess.check_output(['git', 'describe', '--tags', '--always']).decode('utf-8').strip()
        
        # Clean 'v' prefix if present
        version_clean = git_version.lstrip('v')
        
        # Split out the base version (e.g., extracts "1.0" from "1.0-25-g7b4eabd")
        base_version = version_clean.split('-')[0]
        parts = base_version.split('.')
        
        # Pad strings out to 4 items for the display string (e.g., "1.0.0.0")
        while len(parts) < 4:
            parts.append('0')
            
        # Ensure we only take the first 4 elements 
        string_parts = parts[:4]
        
        # CRITICAL FIX: Convert the string elements into a tuple of true integers
        # Filter out any accidental letters from the base version just in case
        int_parts = []
        for x in string_parts:
            # Keep only the numeric digits if a messy tag slipped through
            digits = ''.join(c for c in x if c.isdigit())
            int_parts.append(int(digits) if digits else 0)
            
        # Return tuple of INTS, dot-separated STRING, and the RAW alphanumeric git string
        return tuple(int_parts), f"{'.'.join(string_parts)}", git_version
    except Exception:
        # Fallback if Git is missing
        return (1, 0, 0, 0), '1.0.0.0', '1.0.0-unknown'

# Gather the version arrays
version_tuple, version_str, git_raw = get_git_version()
current_year = datetime.datetime.now().year

# The rigid Windows metadata template
template = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904b0',
        [StringStruct('CompanyName', 'My Organization'),
        StringStruct('FileDescription', 'Tool for inspecting and classifying model files'),
        StringStruct('FileVersion', '{version_str}'),
        StringStruct('InternalName', 'ModelInspector'),
        StringStruct('LegalCopyright', 'Copyright © {current_year} All rights reserved.'),
        StringStruct('OriginalFilename', 'ModelInspector.exe'),
        StringStruct('ProductName', 'ModelInspector'),
        StringStruct('ProductVersion', '{git_raw}')])
      ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

# Save the version file with UTF-8 encoding
with open("version.txt", "w", encoding="utf-8") as f:
    f.write(template.strip())

print(f"[INFO] Successfully generated version.txt for version: {git_raw}")

