import QtQuick

Item {
    id: root
    property var item: null
    property bool isTrack: false

    Column {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: 18
        spacing: 12
        visible: root.item !== null

        // big square art
        Rectangle {
            width: parent.width
            height: width
            radius: Theme.radiusSm
            color: Theme.glassSoft
            clip: true
            Image {
                anchors.fill: parent
                source: root.item ? (root.item.image || "") : ""
                fillMode: Image.PreserveAspectCrop
                visible: source != ""
                asynchronous: true
            }
            Text {
                anchors.centerIn: parent
                visible: !root.item || (root.item.image || "") === ""
                text: "♫"
                color: Theme.subtext
                font.pixelSize: 48
            }
        }

        Text {
            width: parent.width
            text: root.item ? root.item.name : ""
            color: Theme.text
            font.pixelSize: 16
            font.bold: true
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        Text {
            width: parent.width
            text: root.item ? (root.isTrack ? root.item.artist : (root.item.owner || "")) : ""
            color: Theme.teal
            font.pixelSize: 13
            elide: Text.ElideRight
        }

        Text {
            width: parent.width
            visible: root.isTrack && root.item
            text: root.item && root.isTrack ? root.item.album : ""
            color: Theme.subtext
            font.pixelSize: 12
            elide: Text.ElideRight
        }

        Row {
            spacing: 8
            visible: root.isTrack && root.item
            Text {
                text: (root.item && root.item.liked) ? "♥ liked" : "♡  press l to like"
                color: (root.item && root.item.liked) ? Theme.accent : Theme.subtext
                font.pixelSize: 12
            }
            Text {
                text: "🖥  press d for Desktop"
                color: Theme.subtext
                font.pixelSize: 12
            }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: root.item === null
        text: "no preview"
        color: Theme.subtext
        font.pixelSize: 12
    }
}
