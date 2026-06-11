import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: root
    property string title: ""
    property var model: []
    property var playlists: []
    property string nowPlayingId: ""

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Text {
            Layout.fillWidth: true
            Layout.leftMargin: 20
            Layout.topMargin: 14
            Layout.bottomMargin: 8
            text: root.title
            color: Theme.text
            font.pixelSize: 18
            font.bold: true
            elide: Text.ElideRight
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            Layout.bottomMargin: 8
            clip: true
            spacing: 2
            model: root.model
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: TrackRow {
                required property var modelData
                width: ListView.view.width
                track: modelData
                playlists: root.playlists
                playing: modelData.id === root.nowPlayingId
            }
        }
    }
}
