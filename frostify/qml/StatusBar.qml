import QtQuick

Item {
    id: root
    property var np: ({ "active": false })
    property string position: "0/0"
    signal pickDevice()

    function pct() {
        if (!np.active || !np.durationMs) return 0
        return Math.round(np.progressMs / np.durationMs * 100)
    }

    function deviceGlyph(type) {
        switch (("" + type).toLowerCase()) {
            case "computer":   return "💻"
            case "smartphone": return "📱"
            case "tablet":     return "📱"
            case "speaker":    return "🔊"
            case "tv":         return "📺"
            case "castvideo":  return "📺"
            case "avr":
            case "stb":
            case "gameconsole": return "🎮"
            case "automobile": return "🚗"
            default:           return "🔈"
        }
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
                text: root.np.rateLimited ? "⚠ LIMITED"
                      : !root.np.active ? "■ STOPPED"
                      : (root.np.isPlaying ? "▶ PLAYING" : "⏸ PAUSED")
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
            text: root.np.rateLimited ? "Spotify rate-limited this app — pausing calls (clears on its own)"
                  : root.np.active ? (root.np.name + "  ·  " + root.np.artist)
                  : (root.np.private ? "private session — turn it off in Spotify to see the track"
                     : "nothing playing")
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

        // device badge — shows where audio is playing; click to switch
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            height: 22; width: devRow.implicitWidth + 16; radius: Theme.radiusXs
            color: devHover.hovered ? Theme.accentSoft : Theme.badge
            border.color: devHover.hovered ? Theme.accent : "transparent"
            border.width: 1
            Behavior on color { ColorAnimation { duration: 120 } }
            Row {
                id: devRow
                anchors.centerIn: parent
                spacing: 5
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.deviceGlyph(root.np.deviceType); font.pixelSize: 11
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.np.deviceName ? root.np.deviceName : "no device"
                    color: root.np.deviceName ? Theme.text : Theme.subtext
                    font.pixelSize: 11; font.bold: true
                }
            }
            HoverHandler { id: devHover }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.pickDevice()
            }
        }

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
