import QtQuick
import QtQuick.Controls.Basic

Item {
    id: root
    property var model: []
    property int cursor: 0
    property bool active: false
    signal clicked(int index)

    onCursorChanged: if (active) lv.positionViewAtIndex(cursor, ListView.Contain)

    ListView {
        id: lv
        anchors.fill: parent
        anchors.margins: 6
        clip: true
        spacing: 2
        model: root.model
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        delegate: Rectangle {
            required property var modelData
            required property int index
            width: ListView.view.width
            height: 30
            radius: Theme.radiusSm
            color: index === root.cursor ? (root.active ? Theme.sel : Theme.selDim)
                 : (hover.hovered ? Theme.glassSoft : "transparent")

            HoverHandler { id: hover }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.clicked(index)
            }

            Row {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 8
                spacing: 8
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.pinned ? "📌"
                        : modelData.id === "liked"  ? "♥"
                        : modelData.id === "recent" ? "🕘"
                        : "♫"
                    color: index === root.cursor && root.active ? Theme.selText : Theme.teal
                    font.pixelSize: 13
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 28
                    text: modelData.name
                    color: index === root.cursor && root.active ? Theme.selText : Theme.text
                    font.pixelSize: 13
                    elide: Text.ElideRight
                }
            }
        }
    }
}
