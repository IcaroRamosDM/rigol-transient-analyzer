Unicode True
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!ifndef APP_DIR
!error "APP_DIR is required"
!endif
!ifndef OUTPUT_DIR
!error "OUTPUT_DIR is required"
!endif
!ifndef VERSION
!error "VERSION is required"
!endif
Name "Rigol Transient Analyzer"
OutFile "${OUTPUT_DIR}/RigolTransientAnalyzer-${VERSION}-windows-x64-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\RigolTransientAnalyzer"
InstallDirRegKey HKCU "Software\RigolTransientAnalyzer" "InstallPath"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "Rigol Transient Analyzer"
VIAddVersionKey /LANG=1033 "FileDescription" "Rigol Transient Analyzer Setup"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Icaro Ramos Rodrigues dos Santos"
!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\RigolTransientAnalyzer.exe"
!define MUI_FINISHPAGE_LINK "GitHub / Manual"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/IcaroRamosDM/rigol-transient-analyzer"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "PortugueseBR"

Function .onInit
  SetShellVarContext current
  SetRegView 64
  ${IfNot} ${IsNativeAMD64}
    MessageBox MB_OK|MB_ICONSTOP "This package requires Windows x64." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  ReadRegStr $0 HKLM "SOFTWARE\Microsoft\Windows NT\CurrentVersion" "CurrentBuildNumber"
  IntCmp $0 18362 supported unsupported supported
  unsupported:
    MessageBox MB_OK|MB_ICONSTOP "Windows 10 version 1903 or newer is required." /SD IDOK
    SetErrorLevel 2
    Abort
  supported:
FunctionEnd

Function StopForUpdate
  IfFileExists "$INSTDIR\RigolTransientAnalyzer.exe" 0 done
  ExecWait '"$INSTDIR\RigolTransientAnalyzer.exe" --shutdown --quiet' $0
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "Conclua ou cancele o ensaio antes de atualizar. / Finish or cancel the measurement before updating." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  done:
FunctionEnd

Section "Rigol Transient Analyzer" Main
  SectionIn RO
  Call StopForUpdate
  SetOutPath "$INSTDIR"
  File /r "${APP_DIR}/*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\RigolTransientAnalyzer" "InstallPath" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer" "DisplayName" "Rigol Transient Analyzer"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer" "Publisher" "Icaro Ramos Rodrigues dos Santos"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer" "DisplayIcon" "$INSTDIR\RigolTransientAnalyzer.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer" "URLInfoAbout" "https://github.com/IcaroRamosDM/rigol-transient-analyzer"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\Rigol Transient Analyzer"
  CreateShortcut "$SMPROGRAMS\Rigol Transient Analyzer\Rigol Transient Analyzer.lnk" "$INSTDIR\RigolTransientAnalyzer.exe"
  CreateShortcut "$SMPROGRAMS\Rigol Transient Analyzer\Resultados.lnk" "$INSTDIR\RigolTransientAnalyzer.exe" "--open-results"
  CreateShortcut "$SMPROGRAMS\Rigol Transient Analyzer\Encerrar aplicativo.lnk" "$INSTDIR\RigolTransientAnalyzer.exe" "--shutdown"
  WriteINIStr "$SMPROGRAMS\Rigol Transient Analyzer\Manual.url" "InternetShortcut" "URL" "https://github.com/IcaroRamosDM/rigol-transient-analyzer/blob/main/README.md"
SectionEnd

Section /o "Atalho na Área de Trabalho / Desktop shortcut" Desktop
  CreateShortcut "$DESKTOP\Rigol Transient Analyzer.lnk" "$INSTDIR\RigolTransientAnalyzer.exe"
SectionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  ExecWait '"$INSTDIR\RigolTransientAnalyzer.exe" --shutdown --quiet' $0
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "Conclua ou cancele o ensaio antes de desinstalar. / Finish or cancel the measurement before uninstalling." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
FunctionEnd

Section "Uninstall"
  ; Generated exact file list. Unknown files and all user measurements are preserved.
  !include "${UNINSTALL_LIST}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\Rigol Transient Analyzer.lnk"
  Delete "$SMPROGRAMS\Rigol Transient Analyzer\Rigol Transient Analyzer.lnk"
  Delete "$SMPROGRAMS\Rigol Transient Analyzer\Resultados.lnk"
  Delete "$SMPROGRAMS\Rigol Transient Analyzer\Encerrar aplicativo.lnk"
  Delete "$SMPROGRAMS\Rigol Transient Analyzer\Manual.url"
  RMDir "$SMPROGRAMS\Rigol Transient Analyzer"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RigolTransientAnalyzer"
  DeleteRegKey HKCU "Software\RigolTransientAnalyzer"
SectionEnd
