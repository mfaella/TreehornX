enum ReturnPC {
    B2, B3, RET
};

struct Node {
	int value;
	struct Node* left;
	struct Node* right;
	struct Node* parent;
	enum ReturnPC retpc;
	int min;
	int max;
};

void isbst_prepost(struct Node* root) {
	struct Node* current;
	struct Node* newNode;
	struct Node* tmp;
	struct Node* null;
	int return_min;
	int return_max;
	int tmp_value;
	enum ReturnPC tmp_retpc;

	// precondition
	current = root;
	if(!root) {
        return_min = 0;
        return_max = 0;
	}
	else {
		root->parent = null; //tmp is null
		START:
        current->retpc = B2;
		tmp = current->left; //scende a sinistra
		if(!tmp) {
            return_min = 0;
            return_max = 0;
            goto MyReturn;
		}
		tmp = current; // rewind (sale nel padre)
		current = current->left; //scende a sinistra
		current->parent = tmp;
		goto START;

		B2:
		//begin <blocco2-new>
		tmp = current->left; // scende nel sinistro
        tmp_value = current->value;
		if(tmp) {
            current->min = return_min; //risale
            if(tmp_value < return_max) {
                return;
            }
       	}
        else {
      		current->min = tmp_value;
       	}
       	//end <blocco2-new>
        tmp = current->right; // scendo nel destro
        current->retpc = B3;
        if(!tmp) {
            return_min = 0;
            return_max = 0;
            goto MyReturn;
        }
        tmp = current; // risale
        current = current->right; // riscende nel destro
        current->parent = tmp;
        goto START;

        B3:
        //begin <blocco3-new>
        tmp = current->right;
        tmp_value = current->value;
        if(tmp) {
            current->max = return_max;
            if(tmp_value > return_min) {
                return;
            }
       	}
       	else {
      		current->max = tmp_value;
       	}
       	return_min = current->min;
       	return_max = current->max;
       	current->retpc = RET;
        goto MyReturn;

       	MyReturn:
        tmp_retpc = current->retpc;
        tmp = current->parent; // sale nel padre
       	if(tmp || tmp_retpc != RET) {
            if(tmp_retpc == B2) {
                goto B2;
            }
            else if(tmp_retpc == B3) {
                goto B3;
            }
            else if(tmp_retpc == RET) {
               	current = tmp;
                goto MyReturn;
            }
        }
    }

	// function


	// precondition
	current = root;
	if(!root) {
        return_min = 0;
        return_max = 0;
	}
	else {
		START_POST:
        current->retpc = B2;
		tmp = current->left; //scende a sinistra
		if(!tmp) {
            return_min = 0;
            return_max = 0;
            goto MyReturn_POST;
		}
		tmp = current; // rewind (sale nel padre)
		current = current->left; //scende a sinistra
		goto START_POST;

		B2_POST:
		//begin <blocco2-new>
		tmp = current->left; // scende nel sinistro
        tmp_value = current->value;
		if(tmp) {
            current->min = return_min; //risale
            if(tmp_value < return_max) {
                tmp_value = null->value;
            }
       	}
        else {
      		current->min = tmp_value;
       	}
       	//end <blocco2-new>
        tmp = current->right; // scendo nel destro
        current->retpc = B3;
        if(!tmp) {
            return_min = 0;
            return_max = 0;
            goto MyReturn_POST;
        }
        tmp = current; // risale
        current = current->right; // riscende nel destro
        goto START_POST;

        B3_POST:
        //begin <blocco3-new>
        tmp = current->right;
        tmp_value = current->value;
        if(tmp) {
            current->max = return_max;
            if(tmp_value > return_min) {
                tmp_value = null->value;
            }
       	}
       	else {
      		current->max = tmp_value;
       	}
       	return_min = current->min;
       	return_max = current->max;
       	current->retpc = RET;
        goto MyReturn_POST;

       	MyReturn_POST:
        tmp_retpc = current->retpc;
        tmp = current->parent; // sale nel padre
       	if(!tmp && tmp_retpc == RET) return;
        if(tmp_retpc == B2) {
            goto B2_POST;
        }
        else if(tmp_retpc == B3) {
            goto B3_POST;
        }
        else if(tmp_retpc == RET) {
           	current = tmp;
            goto MyReturn_POST;
        }
    }
}
