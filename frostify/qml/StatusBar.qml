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
            width: Math.min(implicitWidth, root.width - 510)
        }
    }

    // right: progress + position badges
    Row {
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        // frostify-only volume (spotifyd's MPRIS device level, not the system mixer)
        Item {
            id: vol
            anchors.verticalCenter: parent.verticalCenter
            width: 132; height: 22
            visible: root.np.active

            // value from the backend, except while the user is dragging the handle
            property real npFrac: (root.np.active && root.np.volume !== undefined)
                                  ? root.np.volume / 100 : 0
            property real dragFrac: 0
            property bool dragging: false
            property real frac: dragging ? dragFrac : npFrac

            Text {
                id: spk
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: 16
                text: vol.frac <= 0 ? "🔇" : (vol.frac < 0.5 ? "🔉" : "🔊")
                font.pixelSize: 12
                color: Theme.subtext
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    // click the speaker to mute / restore
                    onClicked: {
                        if (vol.frac > 0) { vol._premute = vol.frac; backend.setVolume(0) }
                        else { backend.setVolume(Math.round((vol._premute || 0.7) * 100)) }
                    }
                }
                property real _premute: 0.7
            }

            Item {
                id: slider
                anchors.left: spk.right; anchors.leftMargin: 6
                anchors.right: volPct.left; anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                height: parent.height          // tall hit area; track is drawn centered

                Rectangle {                    // track
                    id: track
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    height: 4; radius: 2
                    color: Theme.badge

                    Rectangle {                // fill
                        anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                        width: parent.width * vol.frac
                        height: parent.height; radius: 2
                        color: Theme.accent
                    }
                }
                Rectangle {                    // handle
                    width: 11; height: 11; radius: 5.5
                    color: Theme.text
                    anchors.verticalCenter: parent.verticalCenter
                    x: Math.max(0, Math.min(slider.width - width,
                                            slider.width * vol.frac - width / 2))
                }

                Timer {                        // throttle live audio updates while dragging
                    id: volThrottle
                    interval: 50
                    onTriggered: backend.setVolume(Math.round(vol.dragFrac * 100))
                }

                MouseArea {
                    anchors.fill: parent
                    preventStealing: true
                    cursorShape: Qt.PointingHandCursor
                    function apply(mx) {
                        vol.dragFrac = Math.max(0, Math.min(1, mx / width))
                        if (!volThrottle.running) volThrottle.start()
                    }
                    onPressed: (m) => { vol.dragging = true; apply(m.x) }
                    onPositionChanged: (m) => { if (pressed) apply(m.x) }
                    onReleased: {
                        volThrottle.stop()
                        backend.setVolume(Math.round(vol.dragFrac * 100))
                        vol.dragging = false
                    }
                }
            }

            Text {
                id: volPct
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: 30
                horizontalAlignment: Text.AlignRight
                text: Math.round(vol.frac * 100) + "%"
                color: Theme.subtext; font.pixelSize: 11
            }
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            height: 22; width: spTxt.implicitWidth + 16; radius: Theme.radiusXs
            color: Theme.badge
            Text {
                id: spTxt
                anchors.centerIn: parent
                text: "♫ frostify"
                color: Theme.teal; font.pixelSize: 11; font.bold: true
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
