/**
 * Apps Script bridge for the Elevation Dispatch app.
 *
 * Why this exists:
 *   Google service accounts have ZERO personal Drive storage quota. Even when
 *   uploading INTO a folder shared by a real user, files default-own to the
 *   service account, which Google then rejects with "Service Accounts do not
 *   have storage quota". The only no-cost workarounds are (a) paid Workspace
 *   Shared Drives, or (b) this: an Apps Script that runs AS YOU and uses your
 *   personal Drive quota.
 *
 * What it does:
 *   Receives a JSON POST containing a base64-encoded file + filename + mimetype
 *   + folder ID, creates the file in the folder (owned by you), makes it
 *   readable by anyone with the link, and returns the file's view URL.
 *
 * Deploy (one-time):
 *   1. script.google.com -> + New project
 *   2. Replace the default Code.gs with this file's contents
 *   3. Save
 *   4. Deploy -> New deployment -> "Web app"
 *        - Description: "Dispatch upload bridge"
 *        - Execute as: Me
 *        - Who has access: Anyone (a private link, but anyone with the URL can POST)
 *   5. Copy the resulting Web app URL into your Streamlit secrets as
 *      APPS_SCRIPT_UPLOAD_URL.
 *
 * Security note:
 *   The "Anyone" access on the deployment means the URL itself is the secret.
 *   Don't share it. Anyone with the URL can POST and have a file land in your
 *   Drive folder. If the URL leaks, redeploy (new URL).
 */

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var filename = data.filename || ('upload-' + Date.now());
    var mimetype = data.mimetype || 'application/octet-stream';
    var folderId = data.folderId;
    var b64 = data.content_b64 || '';

    if (!folderId) {
      return _json({ error: 'Missing folderId' });
    }
    if (!b64) {
      return _json({ error: 'Missing content_b64' });
    }

    var bytes = Utilities.base64Decode(b64);
    var blob = Utilities.newBlob(bytes, mimetype, filename);
    var folder = DriveApp.getFolderById(folderId);
    var file = folder.createFile(blob);
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);

    return _json({
      url: file.getUrl(),
      id: file.getId(),
      name: file.getName()
    });
  } catch (err) {
    return _json({ error: String(err) });
  }
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
