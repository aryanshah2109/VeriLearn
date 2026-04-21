import glob
import os

for file in glob.iglob('.', recursive=True):
    if os.path.isfile(file):
        print(file)