import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: win
    visible: true
    width: 1100
    height: 720
    minimumWidth: 820
    minimumHeight: 520
    color: "transparent"
    title: "frostify"

    property var playlists: []
    property var tracks: []
    property var searchResults: []
    property string viewTitle: "Pick a playlist"
    property string mode: "playlist"      // "playlist" | "search"
    property string currentPlaylistId: ""
    property var np: ({ "active": false })
    property bool loggedIn: false

    function currentList() { return mode === "search" ? searchResults : tracks }

    Component.onCompleted: backend.checkLogin()

    Connections {
        target: backend
        function onLoggedInChanged(ok) {
            win.loggedIn = ok
            if (ok) { backend.loadPlaylists(); backend.startPolling() }
        }
        function onPlaylistsLoaded(list) { win.playlists = list }
        function onTracksLoaded(list, title) { win.tracks = list; win.viewTitle = title; win.mode = "playlist" }
        function onSearchLoaded(list) { win.searchResults = list; win.viewTitle = "Search results"; win.mode = "search" }
        function onNowPlaying(data) { win.np = data }
        function onError(msg) { toast.show(msg, true) }
        function onToast(msg) { toast.show(msg, false) }
    }

    // the single frosted glass surface
    Rectangle {
        anchors.fill: parent
        radius: Theme.radius
        color: Theme.glass
        border.color: Theme.border
        border.width: 1

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 1
            spacing: 0

            // top bar: title + search
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 60

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 20
                    anchors.verticalCenter: parent.verticalCenter
                    text: "frostify"
                    color: Theme.text
                    font.pixelSize: 17
                    font.bold: true
                }

                Rectangle {
                    anchors.right: parent.right
                    anchors.rightMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    width: 320
                    height: 36
                    radius: Theme.radiusSm
                    color: Theme.glassSoft
                    border.color: searchField.activeFocus ? Theme.accent : Theme.border
                    border.width: 1

                    TextField {
                        id: searchField
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        verticalAlignment: TextInput.AlignVCenter
                        placeholderText: "Search songs…"
                        color: Theme.text
                        placeholderTextColor: Theme.subtext
                        font.pixelSize: 13
                        background: Item {}
                        onAccepted: if (text.length) backend.search(text)
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }

            // main row: playlists | tracks
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                Sidebar {
                    Layout.preferredWidth: 250
                    Layout.fillHeight: true
                    model: win.playlists
                    currentId: win.currentPlaylistId
                    onOpened: function(id, name, uri) {
                        win.currentPlaylistId = id
                        backend.openPlaylist(id, name, uri)
                    }
                }

                Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.divider }

                ContentView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    title: win.viewTitle
                    model: win.currentList()
                    playlists: win.playlists
                    nowPlayingId: win.np.active ? win.np.id : ""
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.divider }

            NowPlayingBar {
                Layout.fillWidth: true
                Layout.preferredHeight: 88
                np: win.np
            }
        }
    }

    // login overlay
    Rectangle {
        anchors.fill: parent
        radius: Theme.radius
        color: Theme.glass
        visible: !win.loggedIn

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 16

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "frostify"
                color: Theme.text
                font.pixelSize: 30
                font.bold: true
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "Connect your Spotify account to start"
                color: Theme.subtext
                font.pixelSize: 13
            }
            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                width: 180
                height: 44
                radius: Theme.radiusSm
                color: loginHover.hovered ? Theme.accent : Theme.accentSoft
                border.color: Theme.accent
                border.width: 1
                Behavior on color { ColorAnimation { duration: 120 } }
                HoverHandler { id: loginHover }
                Text {
                    anchors.centerIn: parent
                    text: "Log in with Spotify"
                    color: loginHover.hovered ? "white" : Theme.text
                    font.pixelSize: 13
                    font.bold: true
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.login()
                }
            }
        }
    }

    Toast { id: toast }
}
