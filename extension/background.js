const NATIVE_HOST = "com.claude.session.bridge";
const COOKIE_URL = "https://claude.ai";
const COOKIE_NAME = "sessionKey";

async function getSessionKey() {
  const cookie = await chrome.cookies.get({
    url: COOKIE_URL,
    name: COOKIE_NAME,
  });
  return cookie ? cookie.value : null;
}

function sendToNativeHost(sessionKey) {
  chrome.runtime.sendNativeMessage(NATIVE_HOST, { sessionKey }, (resp) => {
    if (chrome.runtime.lastError) {
      console.error("[Claude Bridge]", chrome.runtime.lastError.message);
    } else {
      console.log("[Claude Bridge] sync result:", resp);
    }
  });
}

async function syncSessionKey() {
  const sk = await getSessionKey();
  if (sk && sk.startsWith("sk-ant-sid")) {
    sendToNativeHost(sk);
  }
}

// Auto-sync when the sessionKey cookie changes
chrome.cookies.onChanged.addListener((info) => {
  if (
    info.cookie.domain.includes("claude.ai") &&
    info.cookie.name === COOKIE_NAME &&
    !info.removed
  ) {
    syncSessionKey();
  }
});

// Sync on extension install / browser startup
chrome.runtime.onInstalled.addListener(() => syncSessionKey());
chrome.runtime.onStartup.addListener(() => syncSessionKey());
