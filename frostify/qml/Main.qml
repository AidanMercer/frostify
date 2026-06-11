import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: win
    visible: true
    width: 1180
    height: 760
    minimumWidth: 900
    minimumHeight: 540
    color: "transparent"
    title: "frostify"

    property var playlists: []
    property var tracks: []
    property var searchResults: []
    property string mode: "playlist"          // "playlist" | "search"
    property string openedName: ""
    property var np: ({ "active": false })
    property bool loggedIn: false

    // yazi-style cursor state
    property string activePane: "playlists"    // "playlists" | "tracks"
    property int plCursor: 0
    property int trCursor: 0

    function curTracks() { return mode === "search" ? searchResults : tracks }
    function previewItem() {
        return activePane === "playlists" ? (playlists[plCursor] || null)
                                          : (curTracks()[trCursor] || null)
    }
    function fmtTime(ms) {
        if (!ms || ms < 0) return "0:00"
        var s = Math.floor(ms / 1000), m = Math.floor(s / 60)
        return m + ":" + ((s % 60) < 10 ? "0" : "") + (s % 60)
    }

    // ---- navigation ----
    function moveCursor(d) {
        if (activePane === "playlists") {
            if (playlists.length)
                plCursor = Math.max(0, Math.min(playlists.length - 1, plCursor + d))
        } else {
            var n = curTracks().length
            if (n) trCursor = Math.max(0, Math.min(n - 1, trCursor + d))
        }
    }
    function openPlaylist(p) {
        if (!p) return
        win.openedName = p.name
        backend.openPlaylist(p.id, p.name, p.uri)
        win.activePane = "tracks"
        win.trCursor = 0
    }
    function enterOrPlay() {
        if (activePane === "playlists") openPlaylist(playlists[plCursor])
        else {
            var t = curTracks()[trCursor]
            if (t) backend.playTrack(t.uri, t.contextUri || "")
        }
    }

    Component.onCompleted: backend.checkLogin()

    Connections {
        target: backend
        function onLoggedInChanged(ok) {
            win.loggedIn = ok
            if (ok) { backend.loadPlaylists(); backend.startPolling(); keys.forceActiveFocus() }
        }
        function onPlaylistsLoaded(list) { win.playlists = list }
        function onTracksLoaded(list, title) {
            win.tracks = list; win.openedName = title; win.mode = "playlist"
        }
        function onSearchLoaded(list) {
            win.searchResults = list; win.openedName = "search: " + searchField.text
            win.mode = "search"; win.activePane = "tracks"; win.trCursor = 0
        }
        function onNowPlaying(data) { win.np = data }
        function onError(msg) { toast.show(msg, true) }
        function onToast(msg) { toast.show(msg, false) }
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.radius
        color: Theme.bg
        border.color: Theme.border
        border.width: 1

        // invisible key catcher holds focus for navigation
        Item {
            id: keys
            anchors.fill: parent
            focus: true
            Keys.onUpPressed: win.moveCursor(-1)
            Keys.onDownPressed: win.moveCursor(1)
            Keys.onLeftPressed: win.activePane = "playlists"
            Keys.onRightPressed: win.enterOrPlay()
            Keys.onReturnPressed: win.enterOrPlay()
            Keys.onEnterPressed: win.enterOrPlay()
            Keys.onSpacePressed: backend.togglePlay()
            Keys.onPressed: function(e) {
                if (e.key === Qt.Key_Slash) { searchField.forceActiveFocus(); e.accepted = true }
                else if (e.text === "l" && win.previewItem() && win.activePane === "tracks") {
                    var t = win.previewItem()
                    backend.toggleLike(t.id, !t.liked); e.accepted = true
                }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 1
            spacing: 0

            // ---- breadcrumb ----
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 40

                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    Text { text: "playlists"; color: Theme.subtext; font.pixelSize: 13 }
                    Text { text: "/"; color: Theme.subtext; font.pixelSize: 13; visible: win.openedName !== "" }
                    Text {
                        text: win.openedName; color: Theme.teal; font.pixelSize: 13; font.bold: true
                        visible: win.openedName !== ""
                    }
                }

                Row {
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10

                    Rectangle {
                        width: 220; height: 28
                        anchors.verticalCenter: parent.verticalCenter
                        radius: Theme.radiusSm
                        color: Theme.glassSoft
                        border.color: searchField.activeFocus ? Theme.accent : Theme.border
                        border.width: 1
                        Text {
                            visible: searchField.text === "" && !searchField.activeFocus
                            anchors.left: parent.left; anchors.leftMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            text: "/  search songs"; color: Theme.subtext; font.pixelSize: 12
                        }
                        TextField {
                            id: searchField
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10
                            verticalAlignment: TextInput.AlignVCenter
                            color: Theme.text; font.pixelSize: 12
                            background: Item {}
                            onAccepted: if (text.length) { backend.search(text); keys.forceActiveFocus() }
                            Keys.onEscapePressed: { text = ""; keys.forceActiveFocus() }
                        }
                    }

                    Rectangle {
                        width: 26; height: 26
                        anchors.verticalCenter: parent.verticalCenter
                        radius: Theme.radiusXs
                        color: Theme.accentSoft
                        border.color: Theme.accent; border.width: 1
                        Text { anchors.centerIn: parent; text: "1"; color: Theme.accent; font.pixelSize: 13; font.bold: true }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }

            // ---- three panes ----
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                Sidebar {
                    Layout.preferredWidth: 210
                    Layout.fillHeight: true
                    model: win.playlists
                    cursor: win.plCursor
                    active: win.activePane === "playlists"
                    onClicked: function(i) { win.plCursor = i; win.openPlaylist(win.playlists[i]) }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.divider }

                ContentView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: win.curTracks()
                    playlists: win.playlists
                    cursor: win.trCursor
                    active: win.activePane === "tracks"
                    nowPlayingId: win.np.active ? win.np.id : ""
                    onClicked: function(i) {
                        win.activePane = "tracks"; win.trCursor = i
                        var t = win.curTracks()[i]
                        if (t) backend.playTrack(t.uri, t.contextUri || "")
                    }
                    onMoved: function(i) { win.activePane = "tracks"; win.trCursor = i }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.divider }

                PreviewPane {
                    Layout.preferredWidth: 300
                    Layout.fillHeight: true
                    item: win.previewItem()
                    isTrack: win.activePane === "tracks"
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }

            StatusBar {
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                np: win.np
                position: win.activePane === "playlists"
                    ? (win.playlists.length ? (win.plCursor + 1) + "/" + win.playlists.length : "0/0")
                    : (win.curTracks().length ? (win.trCursor + 1) + "/" + win.curTracks().length : "0/0")
            }
        }
    }

    // ---- login overlay ----
    Rectangle {
        anchors.fill: parent
        radius: Theme.radius
        color: Theme.bg
        visible: !win.loggedIn

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 16
            Text { Layout.alignment: Qt.AlignHCenter; text: "frostify"; color: Theme.text; font.pixelSize: 30; font.bold: true }
            Text { Layout.alignment: Qt.AlignHCenter; text: "Connect your Spotify account"; color: Theme.subtext; font.pixelSize: 13 }
            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                width: 180; height: 44; radius: Theme.radiusSm
                color: loginHover.hovered ? Theme.accent : Theme.accentSoft
                border.color: Theme.accent; border.width: 1
                Behavior on color { ColorAnimation { duration: 120 } }
                HoverHandler { id: loginHover }
                Text {
                    anchors.centerIn: parent; text: "Log in with Spotify"
                    color: loginHover.hovered ? Theme.selText : Theme.text
                    font.pixelSize: 13; font.bold: true
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: backend.login() }
            }
        }
    }

    Toast { id: toast }
}
