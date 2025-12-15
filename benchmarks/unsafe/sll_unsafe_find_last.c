struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_hard(struct Node **head) {
    struct Node *curr;
    int l;
    int v1;
    int v2;
    l = 0;
    curr = *head;
    while(curr) { //2
        v1 = curr->data;
        curr = curr->next;
        l = l + 1; //5
    }
    curr = *head; //6
    while(l > 1) { //7
        curr = curr->next; //8
        l = l - 1;
    }
    if (curr != 0) { //10
        v2 = curr->data;
        if (v1 == v2) { //12
            curr = 0;
            curr = curr->next;
        }
    }
    return;
}