
struct Node {
    int data;
    struct Node* next;
};

void sll_safe_insert_sorted(struct Node* root, int value) {
    struct Node* newNode;
    struct Node* parent;
    struct Node* current;
    int temp_data;

    current = root;

    while (current) {
        temp_data = current->data;
        if (value >= temp_data) { //7
            parent = current; //5
            current = current->next;
        }
        else {
            goto BREAK;
        }
    }
    BREAK:

    newNode = malloc(sizeof(struct Node));
    newNode->data = value;
    newNode->next = current;

    if (parent) {
        parent->next = newNode;
    }
    else {
        root = newNode;
    }
}
