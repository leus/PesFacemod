cls
mkdir workdir
mkdir workdir\PesFacemod\
mkdir workdir\PesFacemod\PesFacemod

cd workdir
del /q /s PesFacemod\
copy ..\PesFacemod\* PesFacemod\PesFacemod\
robocopy ..\Tools PesFacemod\Tools /is /it /e
copy ..\__init__.py PesFacemod\
copy ..\icon.png PesFacemod\
del PesFacemod.zip
zip -r PesFacemod.zip PesFacemod\*
del /q "%appdata%\Blender Foundation\Blender\2.82\scripts\addons\__pycache__\*"
unzip -o PesFacemod.zip -d "%appdata%\Blender Foundation\Blender\2.82\scripts\addons"
"D:\Program Files\Blender Foundation\Blender 2.82\blender.exe"
cd ..