import os
from pathlib import Path
import shutil

def FileHandler(foldertozip, zipname, image_main=None):
    print("Zip File")
    BASE_DIR = Path(__file__).resolve().parent.parent
    image_main = image_main or os.path.join(BASE_DIR, 'frontend/src/imageFile/')
    media_path = os.path.join(BASE_DIR,'frontend/src/imageFile/media')
    media_path1 = '/imageFile/media'
    zip_path = os.path.join(str(image_main) ,'zip')
    
    iszip = os.path.isdir(zip_path)
        
    if iszip == False:
        os.mkdir(zip_path)
        print("Done Created " + str(zip_path))
    else:
        print("Already created") 
        pass
    
    test2 = []



    list = os.listdir(foldertozip)

    for i in list:
        path = os.path.join(foldertozip, i)
        path = path.replace("\\", "/")
        test2.append(path)

    path1 = foldertozip
    path1 = path1.replace("\\", "/")
    path2 = zip_path
    dir_zip = zipname.split(".")[0]
    

    doneZip=os.path.join(path2, dir_zip+".zip")
    isCheck = os.path.isdir(doneZip)
    if isCheck == False:
        shutil.make_archive(os.path.join(path2, dir_zip), 'zip', path1 )
        print("Done Zip")
    
    return test2

