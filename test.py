import glob
import os

for file in glob.iglob('data/raw/ncert/**/*.pdf', recursive=True):
    file = os.path.normpath(file)
    print(file)