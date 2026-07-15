// 툴바 아이콘 클릭 = 사이드패널 열기.
// 이 클릭이 activeTab 권한을 부여하므로, 본문 추출·하이라이트는 항상 아이콘 클릭 후에 가능하다.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);
