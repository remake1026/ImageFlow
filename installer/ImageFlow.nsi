Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "nsDialogs.nsh"
!define KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\ImageFlow"
Name "ImageFlow"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\ImageFlow"
InstallDirRegKey HKCU "${KEY}" "InstallLocation"
RequestExecutionLevel user
ManifestSupportedOS Win10
ManifestDPIAware true
SetCompressor /SOLID lzma
SetCompressorDictSize 32
BrandingText "ImageFlow ${VERSION} | Windows 10 / 11 (64 位)"
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName" "ImageFlow 安装程序"
VIAddVersionKey /LANG=2052 "FileDescription" "ImageFlow 安装向导"
VIAddVersionKey /LANG=2052 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "ImageFlow contributors"
!define MUI_ICON "..\resources\imageflow-logo.ico"
!define MUI_UNICON "..\resources\imageflow-logo.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "此向导将引导您完成 ImageFlow 的安装。$\r$\n$\r$\n支持 Windows 10 1809 及以上、Windows 11（64 位）。无需另外安装 Python。$\r$\n$\r$\n您可以选择安装位置，以及是否创建桌面和开始菜单快捷方式。$\r$\n$\r$\n更新前请先关闭正在运行的 ImageFlow。"
!insertmacro MUI_PAGE_WELCOME
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE CheckDirectory
!insertmacro MUI_PAGE_DIRECTORY
Page custom OptionsCreate OptionsLeave
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\ImageFlow.exe"
!define MUI_FINISHPAGE_RUN_TEXT "运行 ImageFlow"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "SimpChinese"
Var DesktopChoice
Var MenuChoice
Var DesktopControl
Var MenuControl
Var MutexHandle

Function .onInit
  SetShellVarContext current
  SetRegView 64
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "ImageFlow 需要 64 位 Windows 10 或 Windows 11。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_OK|MB_ICONSTOP "ImageFlow 需要 Windows 10 1809 或更高版本。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  ReadRegStr $0 HKLM "SOFTWARE\Microsoft\Windows NT\CurrentVersion" "CurrentBuildNumber"
  ${If} $0 < 17763
    MessageBox MB_OK|MB_ICONSTOP "请先将 Windows 更新至 Windows 10 1809 或更高版本。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\ImageFlowSetup") p .r0 ?e'
  StrCpy $MutexHandle $0
  Pop $1
  ${If} $1 = 183
    MessageBox MB_OK|MB_ICONSTOP "已有 ImageFlow 安装程序正在运行。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  StrCpy $DesktopChoice ${BST_CHECKED}
  StrCpy $MenuChoice ${BST_CHECKED}
  ClearErrors
  ReadRegDWORD $0 HKCU "${KEY}" "DesktopShortcut"
  ${IfNot} ${Errors}
    StrCpy $DesktopChoice $0
  ${EndIf}
  ClearErrors
  ReadRegDWORD $0 HKCU "${KEY}" "StartMenuShortcut"
  ${IfNot} ${Errors}
    StrCpy $MenuChoice $0
  ${EndIf}
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/DESKTOP=" $1
  ${IfNot} ${Errors}
    StrCpy $DesktopChoice $1
  ${EndIf}
  ClearErrors
  ${GetOptions} $0 "/STARTMENU=" $1
  ${IfNot} ${Errors}
    StrCpy $MenuChoice $1
  ${EndIf}
FunctionEnd

Function OptionsCreate
  !insertmacro MUI_HEADER_TEXT "安装选项" "选择要创建的快捷方式。"
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateCheckbox} 0u 15u 100% 16u "创建桌面快捷方式"
  Pop $DesktopControl
  ${NSD_SetState} $DesktopControl $DesktopChoice
  ${NSD_CreateCheckbox} 0u 48u 100% 16u "创建开始菜单快捷方式"
  Pop $MenuControl
  ${NSD_SetState} $MenuControl $MenuChoice
  ${NSD_CreateLabel} 12u 78u 90% 38u "首次安装时均默认勾选，您可以按需取消。$\r$\n安装完成后，也可以直接运行安装目录中的 ImageFlow.exe。"
  Pop $0
  nsDialogs::Show
FunctionEnd

Function OptionsLeave
  ${NSD_GetState} $DesktopControl $DesktopChoice
  ${NSD_GetState} $MenuControl $MenuChoice
FunctionEnd

; Accept only an empty folder or an existing ImageFlow installation.
Function CheckDirectory
  ${GetRoot} "$INSTDIR" $0
  ${If} $INSTDIR == $0
  ${OrIf} $INSTDIR == "$0\"
    Goto bad_directory
  ${EndIf}
  IfFileExists "$INSTDIR\ImageFlow.exe" directory_ok
  FindFirst $0 $1 "$INSTDIR\*"
  directory_loop:
    StrCmp $1 "" directory_empty
    StrCmp $1 "." directory_next
    StrCmp $1 ".." directory_next
    FindClose $0
    Goto bad_directory
  directory_next:
    FindNext $0 $1
    Goto directory_loop
  directory_empty:
    FindClose $0
  directory_ok:
    Return
  bad_directory:
    MessageBox MB_OK|MB_ICONSTOP "请选择空文件夹或已有 ImageFlow 的安装文件夹，不要选择磁盘根目录或其他软件的目录。" /SD IDOK
    SetErrorLevel 2
    Abort
FunctionEnd

!macro CheckNotRunning PREFIX
  IfFileExists "$INSTDIR\ImageFlow.exe" 0 ${PREFIX}not_running
  ClearErrors
  FileOpen $0 "$INSTDIR\ImageFlow.exe" a
  IfErrors 0 ${PREFIX}close_probe
  MessageBox MB_OK|MB_ICONSTOP "请先关闭此安装目录中正在运行的 ImageFlow，再重试。" /SD IDOK
  SetErrorLevel 3
  Abort
  ${PREFIX}close_probe:
    FileClose $0
  ${PREFIX}not_running:
!macroend

Section "ImageFlow"
  Call CheckDirectory
  !insertmacro CheckNotRunning "install_"
  SetOutPath "$INSTDIR"
  SetOverwrite on
  File /r "${PAYLOAD}\*.*"
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "${KEY}" "DisplayName" "ImageFlow"
  WriteRegStr HKCU "${KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${KEY}" "Publisher" "ImageFlow"
  WriteRegStr HKCU "${KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${KEY}" "DisplayIcon" "$INSTDIR\ImageFlow.exe,0"
  WriteRegStr HKCU "${KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${KEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegStr HKCU "${KEY}" "URLInfoAbout" "https://github.com/remake1026/ImageFlow"
  WriteRegDWORD HKCU "${KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${KEY}" "EstimatedSize" ${SIZE_KB}
  ${If} $DesktopChoice == ${BST_CHECKED}
    CreateShortCut "$DESKTOP\ImageFlow.lnk" "$INSTDIR\ImageFlow.exe" "" "$INSTDIR\ImageFlow.exe" 0
  ${Else}
    ReadRegDWORD $0 HKCU "${KEY}" "DesktopShortcut"
    ${If} $0 == 1
      Delete "$DESKTOP\ImageFlow.lnk"
    ${EndIf}
  ${EndIf}
  ${If} $MenuChoice == ${BST_CHECKED}
    CreateDirectory "$SMPROGRAMS\ImageFlow"
    CreateShortCut "$SMPROGRAMS\ImageFlow\ImageFlow.lnk" "$INSTDIR\ImageFlow.exe" "" "$INSTDIR\ImageFlow.exe" 0
    CreateShortCut "$SMPROGRAMS\ImageFlow\卸载 ImageFlow.lnk" "$INSTDIR\Uninstall.exe"
  ${Else}
    ReadRegDWORD $0 HKCU "${KEY}" "StartMenuShortcut"
    ${If} $0 == 1
      Delete "$SMPROGRAMS\ImageFlow\ImageFlow.lnk"
      Delete "$SMPROGRAMS\ImageFlow\卸载 ImageFlow.lnk"
      RMDir "$SMPROGRAMS\ImageFlow"
    ${EndIf}
  ${EndIf}
  WriteRegDWORD HKCU "${KEY}" "DesktopShortcut" $DesktopChoice
  WriteRegDWORD HKCU "${KEY}" "StartMenuShortcut" $MenuChoice
  SetErrorLevel 0
SectionEnd

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  !insertmacro CheckNotRunning "uninstall_"
FunctionEnd

Section "Uninstall"
  ; Delete only packaged files. Never recursively delete user files or AppData.
  !include "${DELETE_MANIFEST}"
  ReadRegStr $0 HKCU "${KEY}" "InstallLocation"
  ${If} $0 == $INSTDIR
    ReadRegDWORD $0 HKCU "${KEY}" "DesktopShortcut"
    ${If} $0 == 1
      Delete "$DESKTOP\ImageFlow.lnk"
    ${EndIf}
    ReadRegDWORD $0 HKCU "${KEY}" "StartMenuShortcut"
    ${If} $0 == 1
      Delete "$SMPROGRAMS\ImageFlow\ImageFlow.lnk"
      Delete "$SMPROGRAMS\ImageFlow\卸载 ImageFlow.lnk"
      RMDir "$SMPROGRAMS\ImageFlow"
    ${EndIf}
    DeleteRegKey HKCU "${KEY}"
  ${EndIf}
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  SetErrorLevel 0
SectionEnd
