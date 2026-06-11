import QtQuick

Item {
    id: root
    property var np: ({ "active": false })
    property string position: "0/0"

    function pct() {
        if (!np.active || !np.durationMs) return 0
        return Math.round(np.progressMs / np.durationMs * 100)
    }

    // left: mode badge + transport
    Row {
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            height: 22
            width: stateTxt.implicitWidth + 18
            radius: Theme.radiusXs
            color: Theme.accent
            Text {
                id: stateTxt
                anchors.centerIn: parent
                text: !root.np.active ? "■ STOPPED" : (root.np.isPlaying ? "▶ PLAYING" : "⏸ PAUSED")
                color: Theme.selText
                font.pixelSize: 11
                font.bold: true
            }
        }

        IconButton { anchors.verticalCenter: parent.verticalCenter; glyph: "⏮"; size: 22; fontSize: 13; fg: Theme.subtext; onClicked: backend.prevTrack() }
        IconButton { anchors.verticalCenter: parent.verticalCenter; glyph: root.np.active && root.np.isPlaying ? "⏸" : "▶"; size: 22; fontSize: 13; fg: Theme.text; onClicked: backend.togglePlay() }
        IconButton { anchors.verticalCenter: parent.verticalCenter; glyph: "⏭"; size: 22; fontSize: 13; fg: Theme.subtext; onClicked: backend.nextTrack() }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.np.active ? (root.np.name + "  ·  " + root.np.artist) : "nothing playing"
            color: root.np.active ? Theme.text : Theme.subtext
            font.pixelSize: 12
            elide: Text.ElideRight
            width: Math.min(implicitWidth, root.width - 360)
        }
    }

    // right: progress + position badges
    Row {
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            height: 22; width: pctTxt.implicitWidth + 16; radius: Theme.radiusXs
            color: Theme.badge
            visible: root.np.active
            Text { id: pctTxt; anchors.centerIn: parent; text: root.pct() + "%"; color: Theme.green; font.pixelSize: 11; font.bold: true }
        }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            height: 22; width: posTxt.implicitWidth + 16; radius: Theme.radiusXs
            color: Theme.accent
            Text { id: posTxt; anchors.centerIn: parent; text: root.position; color: Theme.selText; font.pixelSize: 11; font.bold: true }
        }
    }
}
