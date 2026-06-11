import QtQuick
import QtQuick.Controls.Basic

Item {
    id: root
    property var model: []
    property string currentId: ""
    signal opened(string id, string name, string uri)

    ListView {
        anchors.fill: parent
        anchors.margins: 8
        clip: true
        spacing: 4
        model: root.model
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        delegate: Rectangle {
            required property var modelData
            width: ListView.view.width
            height: 54
            radius: Theme.radiusSm
            color: modelData.id === root.currentId ? Theme.glassStrong
                 : (hover.hovered ? Theme.glassSoft : "transparent")
            Behavior on color { ColorAnimation { duration: 120 } }

            HoverHandler { id: hover }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.opened(modelData.id, modelData.name, modelData.uri)
            }

            Row {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 10

                Rectangle {
                    width: 38; height: 38
                    radius: Theme.radiusXs
                    color: Theme.glassSoft
                    clip: true
                    Image {
                        anchors.fill: parent
                        source: modelData.image
                        fillMode: Image.PreserveAspectCrop
                        visible: modelData.image !== ""
                        asynchronous: true
                    }
                }

                Column {
                    width: parent.width - 48
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text {
                        text: modelData.name
                        color: Theme.text
                        font.pixelSize: 13
                        font.bold: true
                        elide: Text.ElideRight
                        width: parent.width
                    }
                    Text {
                        text: modelData.count + " tracks"
                        color: Theme.subtext
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        width: parent.width
                    }
                }
            }
        }
    }
}
