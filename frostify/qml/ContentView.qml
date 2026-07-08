import QtQuick
import QtQuick.Controls.Basic

Item {
    id: root
    property var model: []
    property var playlists: []
    property int cursor: 0
    property bool active: false
    property string nowPlayingId: ""
    property var chrome: null      // rice theme layer — optional glyph overrides
    signal clicked(int index)
    signal moved(int index)

    function cp(name, fallback) {
        var v = chrome ? chrome[name] : undefined
        return v === undefined ? fallback : v
    }

    onCursorChanged: if (active) lv.positionViewAtIndex(cursor, ListView.Contain)

    function fmtTime(ms) {
        if (!ms || ms < 0) return "0:00"
        var s = Math.floor(ms / 1000), m = Math.floor(s / 60)
        return m + ":" + ((s % 60) < 10 ? "0" : "") + (s % 60)
    }

    Text {
        anchors.centerIn: parent
        visible: root.model.length === 0
        text: "→  open a playlist"
        color: Theme.subtext
        font.pixelSize: 13
    }

    ListView {
        id: lv
        anchors.fill: parent
        anchors.margins: 6
        clip: true
        spacing: 1
        model: root.model
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        delegate: Rectangle {
            id: row
            required property var modelData
            required property int index
            property bool onCursor: index === root.cursor
            property bool isPlaying: modelData.id === root.nowPlayingId
            width: ListView.view.width
            height: 30
            radius: Theme.radiusSm
            color: onCursor ? (root.active ? Theme.sel : Theme.selDim)
                 : (hover.hovered ? Theme.glassSoft : "transparent")

            HoverHandler { id: hover }
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                cursorShape: Qt.PointingHandCursor
                onClicked: function(mouse) {
                    if (mouse.button === Qt.RightButton) { root.moved(index); addMenu.popup() }
                    else root.clicked(index)
                }
            }

            Menu {
                id: addMenu
                Repeater {
                    model: root.playlists.filter(function(p) { return p.id !== "recent" && p.id !== "desktop" })
                    MenuItem {
                        required property var modelData
                        text: "+ " + modelData.name
                        onTriggered: backend.addToPlaylist(row.modelData.uri, modelData.id)
                    }
                }
            }

            Row {
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.right: dur.left
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Text {
                    width: 12
                    text: row.isPlaying ? root.cp("glyphNowPlaying", "▶")
                                        : (row.modelData.liked ? root.cp("glyphLiked", "♥") : "")
                    color: row.onCursor && root.active ? Theme.selText
                         : (row.isPlaying ? Theme.accent : Theme.green)
                    font.pixelSize: 11
                }
                Text {
                    width: parent.width - 20
                    text: row.modelData.name + "   ·   " + row.modelData.artist
                    color: row.onCursor && root.active ? Theme.selText
                         : (row.isPlaying ? Theme.accent : Theme.text)
                    font.pixelSize: 13
                    elide: Text.ElideRight
                }
            }
            Text {
                id: dur
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: root.fmtTime(row.modelData.durationMs)
                color: row.onCursor && root.active ? Theme.selText : Theme.green
                font.pixelSize: 12
            }
        }
    }
}
