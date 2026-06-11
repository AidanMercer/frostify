import QtQuick

Item {
    id: root
    property var np: ({ "active": false })

    // local progress that ticks every second, resynced whenever the backend reports
    property real localProg: 0
    onNpChanged: localProg = (np.active ? np.progressMs : 0)

    function fmtTime(ms) {
        if (!ms || ms < 0) return "0:00"
        var s = Math.floor(ms / 1000)
        var m = Math.floor(s / 60)
        s = s % 60
        return m + ":" + (s < 10 ? "0" : "") + s
    }

    Timer {
        interval: 1000
        repeat: true
        running: root.np.active && root.np.isPlaying
        onTriggered: {
            if (root.localProg < root.np.durationMs)
                root.localProg += 1000
        }
    }

    // left: art + title/artist
    Row {
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 12
        visible: root.np.active

        Rectangle {
            width: 52; height: 52
            anchors.verticalCenter: parent.verticalCenter
            radius: Theme.radiusXs
            color: Theme.glassSoft
            clip: true
            Image {
                anchors.fill: parent
                source: root.np.active ? root.np.image : ""
                fillMode: Image.PreserveAspectCrop
                visible: root.np.active && root.np.image !== ""
                asynchronous: true
            }
        }

        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 3
            width: 200
            Text {
                text: root.np.active ? root.np.name : ""
                color: Theme.text
                font.pixelSize: 13
                font.bold: true
                elide: Text.ElideRight
                width: parent.width
            }
            Text {
                text: root.np.active ? root.np.artist : ""
                color: Theme.subtext
                font.pixelSize: 11
                elide: Text.ElideRight
                width: parent.width
            }
        }

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            glyph: (root.np.active && root.np.liked) ? "♥" : "♡"
            fg: (root.np.active && root.np.liked) ? Theme.accent : Theme.subtext
            size: 32
            fontSize: 16
            onClicked: if (root.np.active) backend.toggleLike(root.np.id, !root.np.liked)
        }
    }

    // center: transport controls + progress
    Column {
        anchors.centerIn: parent
        spacing: 6
        width: 360
        visible: root.np.active

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 14

            IconButton {
                glyph: "⏮"; fontSize: 18; fg: Theme.text
                onClicked: backend.prevTrack()
            }
            IconButton {
                glyph: root.np.active && root.np.isPlaying ? "⏸" : "▶"
                size: 44; fontSize: 22; fg: Theme.text
                onClicked: backend.togglePlay()
            }
            IconButton {
                glyph: "⏭"; fontSize: 18; fg: Theme.text
                onClicked: backend.nextTrack()
            }
        }

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 8

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.fmtTime(root.localProg)
                color: Theme.subtext
                font.pixelSize: 10
                width: 32
                horizontalAlignment: Text.AlignRight
            }

            Rectangle {
                id: bar
                anchors.verticalCenter: parent.verticalCenter
                width: 260; height: 5
                radius: 3
                color: Theme.glassSoft

                Rectangle {
                    height: parent.height
                    radius: 3
                    color: Theme.accent
                    width: (root.np.active && root.np.durationMs > 0)
                           ? parent.width * Math.min(1, root.localProg / root.np.durationMs)
                           : 0
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: function(mouse) {
                        if (root.np.active && root.np.durationMs > 0) {
                            var ms = Math.round(mouse.x / width * root.np.durationMs)
                            root.localProg = ms
                            backend.seek(ms)
                        }
                    }
                }
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.fmtTime(root.np.active ? root.np.durationMs : 0)
                color: Theme.subtext
                font.pixelSize: 10
                width: 32
            }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: !root.np.active
        text: "Nothing playing"
        color: Theme.subtext
        font.pixelSize: 12
    }
}
