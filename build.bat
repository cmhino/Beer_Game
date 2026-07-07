@echo off
rem ============================================================
rem  Beer Game (CISLOG) - gera o executavel unico (Windows)
rem  Requisitos: pip install pyinstaller openpyxl pillow
rem
rem  - logo.jpg     fica EMBUTIDO no .exe (cabecalho do app)
rem  - beergame.ico e o icone do executavel e da janela
rem  No Windows o separador do --add-data e ponto-e-virgula (;).
rem  Para trocar o logo/icone: substitua logo.jpg e gere o
rem  beergame.ico de novo (veja gerar_icone.py), depois rode este script.
rem ============================================================
pyinstaller --onefile --windowed --name BeerGame --clean ^
    --icon beergame.ico ^
    --add-data "logo.jpg;." ^
    --add-data "beergame.ico;." ^
    main.py
echo.
echo Pronto! Executavel unico em dist\BeerGame.exe
echo O logo e o icone ja estao embutidos no .exe.
echo (Se o antivirus reclamar, troque --onefile por --onedir)
pause
