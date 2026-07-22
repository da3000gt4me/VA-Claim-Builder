from PyInstaller.utils.hooks import collect_all
from pathlib import Path
root = Path(SPECPATH).parent
hidden=[]; datas=[]; binaries=[]
for pkg in ["streamlit","pydantic","docx","pypdf","PIL","sqlalchemy","cryptography","openai","httpx","tenacity"]:
    d,b,h=collect_all(pkg); datas+=d; binaries+=b; hidden+=h
datas += [(str(root/"app.py"),"."),(str(root/"core"),"core"),(str(root/"ui"),"ui"),(str(root/"config"),"config"),(str(root/"prompts"),"prompts"),(str(root/"docs"),"docs"),(str(root/"version.json"),"."),(str(root/".env.example"),".")]
a=Analysis([str(root/"desktop_launcher.py")],pathex=[str(root)],binaries=binaries,datas=datas,hiddenimports=hidden,noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name="VAClaimBuilder-Debug",console=True,disable_windowed_traceback=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name="VAClaimBuilder-Debug")
