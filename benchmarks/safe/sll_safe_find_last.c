struct Node {
    int data;
    struct Node *next;
};


void sll_safe_find_last(struct Node *root) {
    struct Node *curr;
    struct Node  *null;
    int l;
    int v1;
    int v2;
    l = 0;
    curr = root;
    while(curr) { //2
        v1 = curr->data;
        curr = curr->next;
        l = l + 1; //5
    }
    curr = root; //6
    while(l > 1) { //7
        curr = curr->next; //8
        l = l - 1;
    }
    if (curr) { //10
        v2 = curr->data;
        if (v1 != v2) { //12
            curr = null->next;
        }
    }
    return;
}
