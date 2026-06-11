import QtQuick
import QtQuick.Controls.Basic

Rectangle {
    id: root
    property var track
    property var playlists: []
    property bool playing: false

    // optimistic local copy so the heart flips instantly on click
    property bool liked: track.liked

    height: 56
    radius: Theme.radiusSm
    color: playing ? Theme.glassStrong : (hover.hovered ? Theme.glassSoft : "transparent")
    Behavior on color { ColorAnimation { duration: 120 } }

    function fmtTime(ms) {
        if (!ms || ms < 0) return "0:00"
        var s = Math.floor(ms / 1000)
        var m = Math.floor(s / 60)
        s = s % 60
        return m + ":" + (s < 10 ? "0" : "") + s
    }

    HoverHandler { id: hover }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: backend.playTrack(root.track.uri, root.track.contextUri)
    }

    Row {
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 12
        spacing: 12

        // accent bar when this is the playing track
        Rectangle {
            width: 3; height: 32
            anchors.verticalCenter: parent.verticalCenter
            radius: 2
            color: root.playing ? Theme.accent : "transparent"
        }

        Rectangle {
            width: 40; height: 40
            anchors.verticalCenter: parent.verticalCenter
            radius: Theme.radiusXs
            color: Theme.glassSoft
            clip: true
            Image {
                anchors.fill: parent
                source: root.track.image
                fillMode: Image.PreserveAspectCrop
                visible: root.track.image !== ""
                asynchronous: true
            }
        }

        Column {
            width: root.width - 320
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Text {
                text: root.track.name
                color: root.playing ? Theme.accent : Theme.text
                font.pixelSize: 13
                font.bold: true
                elide: Text.ElideRight
                width: parent.width
            }
            Text {
                text: root.track.artist
                color: Theme.subtext
                font.pixelSize: 11
                elide: Text.ElideRight
                width: parent.width
            }
        }
    }

    // right-aligned controls: like, add, duration
    Row {
        anchors.right: parent.right
        anchors.rightMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        spacing: 6

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            glyph: root.liked ? "♥" : "♡"
            fg: root.liked ? Theme.accent : Theme.subtext
            size: 32
            fontSize: 16
            onClicked: {
                root.liked = !root.liked
                backend.toggleLike(root.track.id, root.liked)
            }
        }

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            glyph: "+"
            fg: Theme.subtext
            size: 32
            fontSize: 20
            onClicked: addMenu.popup()

            Menu {
                id: addMenu
                Repeater {
                    model: root.playlists
                    MenuItem {
                        required property var modelData
                        text: modelData.name
                        onTriggered: backend.addToPlaylist(root.track.uri, modelData.id)
                    }
                }
            }
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            width: 42
            horizontalAlignment: Text.AlignRight
            text: root.fmtTime(root.track.durationMs)
            color: Theme.subtext
            font.pixelSize: 12
        }
    }
}
