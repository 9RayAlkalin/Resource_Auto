import subprocess
import os
import sys

# Single Chart
def schartTask(dir, path):
    makeOneTask(dir, path)

# Single Folder
def sfileTask(dir, path, output, progress_cb=None, stop_check=None):
    files = [f for f in os.listdir(path) if f.endswith(".pez")]
    total = len(files)
    for i, file in enumerate(files, 1):
        if stop_check is not None and stop_check():
            print("render cancelled")
            return
        command = f"--render {os.path.join(path, file)} --output {output}"
        #makeTask(dir,command)
        makeOneTask(dir, os.path.join(path, file), output)
        if progress_cb is not None:
            progress_cb(i, total, file)

# All Folder
def fileTask(dir, path):
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(".pez"):
                makeTask(dir, root, file)


# Create Task
def makeTask(dir, root, file):
    full_root = os.path.abspath(root)
    input = os.path.join(full_root, file)
    command = f"\"{dir}\" --render {input}"

    print(command)
    process = subprocess.Popen(command, shell=True, stdout=sys.stdout, stderr=sys.stderr)

    process.wait()

def makeOneTask(dir, file, output):
    full_file = os.path.abspath(file)
    full_output = os.path.abspath(output)
    command = f"\"{dir}\" --render {full_file} --output {full_output}"
    
    print(command)
    process = subprocess.Popen(command, shell=True, stdout=sys.stdout, stderr=sys.stderr)

    process.wait()


def fileType(dir):
    for filename in os.listdir(dir):
        if filename in ['EZ','HD','IN','AT']:
            return "Phira"
    return ""
