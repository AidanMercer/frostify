import QtQuick

// full-window overlay that lets the user pick which Spotify device plays audio
Item {
    id: root
    property var model: []
    anchors.fill: parent
    visible: false

    function glyph(type) {
        switch (("" + type).toLowerCase()) {
            case "computer":    return "💻"
            case "smartphone":  return "📱"
            case "tablet":      return "📱"
            case "speaker":     return "🔊"
            case "tv":          return "📺"
            case "castvideo":   return "📺"
            case "avr":
            case "stb":
            case "gameconsole": return "🎮"
            case "automobile":  return "🚗"
            default:            return "🔈"
        }
    }

    // click-away to dismiss
    MouseArea {
        anchors.fill: parent
        onClicked: root.visible = false
    }

    Rectangle {
        id: panel
        width: 300
        height: header.height + 16 + Math.max(1, root.model.length) * 48 + 24
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 44
        radius: Theme.radiusSm
        color: Theme.toastBg
        border.color: Theme.border
        border.width: 1

        // swallow clicks so they don't fall through to the dismiss layer
        MouseArea { anchors.fill: parent }

        Column {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8

            Text {
                id: header
                text: "Connect to a device"
                color: Theme.text
                font.pixelSize: 13
                font.bold: true
            }

            Text {
                visible: root.model.length === 0
                width: parent.width
                text: "No devices found.\nOpen Spotify on a phone, desktop or speaker."
                color: Theme.subtext
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: root.model
                delegate: Rectangle {
                    width: panel.width - 24
                    height: 44
                    radius: Theme.radiusXs
                    color: rowHover.hovered ? Theme.glassSoft : "transparent"
                    HoverHandler { id: rowHover }

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        anchors.right: parent.right
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: root.glyph(modelData.type)
                            font.pixelSize: 18
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 60
                            Text {
                                text: modelData.name
                                color: modelData.isActive ? Theme.green : Theme.text
                                font.pixelSize: 12
                                font.bold: modelData.isActive
                                elide: Text.ElideRight
                                width: parent.width
                            }
                            Text {
                                text: modelData.type + (modelData.isActive ? "  ·  active" : "")
                                color: Theme.subtext
                                font.pixelSize: 10
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "✓"
                            color: Theme.green
                            font.pixelSize: 14
                            visible: modelData.isActive
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!modelData.isActive)
                                backend.transferPlayback(modelData.id)
                            root.visible = false
                        }
                    }
                }
            }
        }
    }
}
