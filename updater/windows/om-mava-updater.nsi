; OM MAVA Updater — Windows installer (NSIS). Built on the Mac by release/updater/windows/build-exe.sh:
;   makensis -DVER=<ver> -DSTAGE=<staged app folder> -DOUT=<setup.exe> om-mava-updater.nsi
; Per-user install (no admin): %LOCALAPPDATA%\OM MAVA Updater, shortcuts on the Desktop and in the Start Menu,
; uninstall entry in Apps & features. Python + Tk ship inside (CHECK VIDEO's vendor-win), so nothing else is needed.
Unicode true
!include "MUI2.nsh"

Name "OM MAVA Updater"
OutFile "${OUT}"
InstallDir "$LOCALAPPDATA\OM MAVA Updater"
RequestExecutionLevel user
SetCompressor /SOLID lzma
VIProductVersion "${VER}.0"
VIAddVersionKey "ProductName" "OM MAVA Updater"
VIAddVersionKey "CompanyName" "MAVA MEDIA"
VIAddVersionKey "FileVersion" "${VER}"
VIAddVersionKey "FileDescription" "OM MAVA Updater — cài và cập nhật OpenMontage"
VIAddVersionKey "LegalCopyright" "© MAVA MEDIA"

!define MUI_ICON "${STAGE}\om-mava-updater.ico"
!define MUI_UNICON "${STAGE}\om-mava-updater.ico"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Mở OM MAVA Updater"
!define MUI_FINISHPAGE_RUN_FUNCTION OpenApp
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Vietnamese"

Function OpenApp
  ExecShell "" "wscript.exe" '"$INSTDIR\launch.vbs"'
FunctionEnd

Section "OM MAVA Updater"
  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\app"                  ; an update of the app itself: no stale files
  File /r "${STAGE}\*"
  CreateShortcut "$DESKTOP\OM MAVA Updater.lnk" "wscript.exe" '"$INSTDIR\launch.vbs"' "$INSTDIR\om-mava-updater.ico" 0
  CreateDirectory "$SMPROGRAMS\OM MAVA Updater"
  CreateShortcut "$SMPROGRAMS\OM MAVA Updater\OM MAVA Updater.lnk" "wscript.exe" '"$INSTDIR\launch.vbs"' "$INSTDIR\om-mava-updater.ico" 0
  CreateShortcut "$SMPROGRAMS\OM MAVA Updater\Gỡ cài đặt OM MAVA Updater.lnk" "$INSTDIR\uninstall.exe"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  !define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\OM MAVA Updater"
  WriteRegStr HKCU "${UNINST}" "DisplayName" "OM MAVA Updater"
  WriteRegStr HKCU "${UNINST}" "DisplayVersion" "${VER}"
  WriteRegStr HKCU "${UNINST}" "Publisher" "MAVA MEDIA"
  WriteRegStr HKCU "${UNINST}" "DisplayIcon" "$INSTDIR\om-mava-updater.ico"
  WriteRegStr HKCU "${UNINST}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "${UNINST}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST}" "NoRepair" 1
SectionEnd

; Removes the app only: the OpenMontage folder, films and keys stay where they are.
Section "Uninstall"
  Delete "$DESKTOP\OM MAVA Updater.lnk"
  RMDir /r "$SMPROGRAMS\OM MAVA Updater"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\OM MAVA Updater"
SectionEnd
